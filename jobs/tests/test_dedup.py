from dataclasses import dataclass

from jobs.dedup import cluster_jobs


@dataclass
class FakeJob:
    source: str
    title: str
    company: str
    description: str = ""


def clusters_by_canonical(jobs):
    return {
        cluster.canonical.source: [duplicate.source for duplicate in cluster.duplicates]
        for cluster in cluster_jobs(jobs)
    }


def test_same_role_from_two_boards_is_one_cluster():
    jobs = [
        FakeJob("remotive", "Senior Python Engineer", "Acme Inc."),
        FakeJob("adzuna", "Senior Python Engineer (m/f/d)", "ACME"),
    ]
    result = cluster_jobs(jobs)
    assert len(result) == 1
    assert len(result[0].duplicates) == 1


def test_company_board_wins_over_aggregator():
    jobs = [
        FakeJob("jooble", "Backend Engineer", "Acme"),
        FakeJob("greenhouse", "Backend Engineer", "Acme"),
    ]
    assert clusters_by_canonical(jobs) == {"greenhouse": ["jooble"]}


def test_longer_description_wins_within_the_same_priority():
    jobs = [
        FakeJob("remotive", "Backend Engineer", "Acme", description="short"),
        FakeJob("arbeitnow", "Backend Engineer", "Acme", description="a much longer description"),
    ]
    assert clusters_by_canonical(jobs) == {"arbeitnow": ["remotive"]}


def test_different_roles_at_one_company_stay_separate():
    jobs = [
        FakeJob("remotive", "Backend Engineer", "Acme"),
        FakeJob("remotive", "Product Designer", "Acme"),
    ]
    assert len(cluster_jobs(jobs)) == 2


def test_same_title_at_different_companies_stays_separate():
    jobs = [
        FakeJob("remotive", "Backend Engineer", "Acme"),
        FakeJob("remotive", "Backend Engineer", "Globex"),
    ]
    assert len(cluster_jobs(jobs)) == 2


def test_word_order_and_extra_words_still_match():
    jobs = [
        FakeJob("remotive", "Senior Backend Engineer", "Acme"),
        FakeJob("adzuna", "Backend Engineer, Senior", "Acme"),
    ]
    assert len(cluster_jobs(jobs)) == 1


def test_frontend_and_backend_are_not_merged():
    jobs = [
        FakeJob("remotive", "Senior Frontend Engineer", "Acme"),
        FakeJob("remotive", "Senior Backend Engineer", "Acme"),
    ]
    assert len(cluster_jobs(jobs)) == 2


def test_missing_company_never_merges():
    jobs = [
        FakeJob("remotive", "Backend Engineer", ""),
        FakeJob("adzuna", "Backend Engineer", ""),
    ]
    assert len(cluster_jobs(jobs)) == 2


def test_empty_input():
    assert cluster_jobs([]) == []


def test_three_copies_collapse_to_one_canonical_and_two_duplicates():
    jobs = [
        FakeJob("adzuna", "Data Analyst", "Globex"),
        FakeJob("jooble", "Data Analyst - Remote", "Globex Ltd"),
        FakeJob("lever", "Data Analyst", "Globex"),
    ]
    result = cluster_jobs(jobs)
    assert len(result) == 1
    assert result[0].canonical.source == "lever"
    assert sorted(job.source for job in result[0].duplicates) == ["adzuna", "jooble"]


def test_description_length_attribute_is_used_when_present():
    @dataclass
    class Ref:
        source: str
        title: str
        company: str
        description_length: int

    jobs = [
        Ref("remotive", "Backend Engineer", "Acme", 10),
        Ref("arbeitnow", "Backend Engineer", "Acme", 900),
    ]
    assert clusters_by_canonical(jobs) == {"arbeitnow": ["remotive"]}
