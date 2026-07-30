"""A hand-maintained skill vocabulary.

Used in two places: the keyword fallback when the LLM cannot parse a CV, and the
rule-based job scorer. Both need the same canonical spellings so that "postgres"
in a CV and "PostgreSQL" in a posting count as the same skill.

Short names like Go, C and R are deliberately matched only through unambiguous
aliases. Matching a bare "go" or "r" produces false positives in every third
sentence of English prose, and a wrong skill match distorts a score more than a
missing one does.
"""

import re

SKILL_ALIASES = {
    "Python": ["python"],
    "JavaScript": ["javascript", "js", "es6"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "Objective-C": ["objective-c", "objective c"],
    "C#": ["c#", "csharp", "c sharp"],
    "C++": ["c++", "cpp"],
    "C": ["ansi c", "c language", "c programming"],
    "Go": ["golang", "go lang"],
    "Rust": ["rust"],
    "Ruby": ["ruby"],
    "PHP": ["php"],
    "Scala": ["scala"],
    "Elixir": ["elixir"],
    "R": ["r language", "rstudio", "r programming"],
    "SQL": ["sql"],
    "Bash": ["bash", "shell scripting", "zsh"],
    "PowerShell": ["powershell"],
    "Django": ["django"],
    "Django REST Framework": ["django rest framework", "drf"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    "Celery": ["celery"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "Express": ["express.js", "expressjs", "express"],
    "NestJS": ["nestjs", "nest.js"],
    "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs"],
    "Vue": ["vue", "vue.js", "vuejs"],
    "Nuxt": ["nuxt", "nuxt.js"],
    "Angular": ["angular", "angularjs"],
    "Svelte": ["svelte", "sveltekit"],
    "React Native": ["react native"],
    "Flutter": ["flutter"],
    "Electron": ["electron"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    "Rails": ["ruby on rails", "rails"],
    "Laravel": ["laravel"],
    "ASP.NET": ["asp.net", "aspnet", ".net core", "dotnet"],
    "GraphQL": ["graphql"],
    "REST APIs": ["rest api", "rest apis", "restful"],
    "gRPC": ["grpc"],
    "WebSockets": ["websocket", "websockets"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Sass": ["sass", "scss"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql", "mariadb"],
    "SQLite": ["sqlite"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "opensearch"],
    "Cassandra": ["cassandra"],
    "DynamoDB": ["dynamodb"],
    "ClickHouse": ["clickhouse"],
    "Snowflake": ["snowflake"],
    "BigQuery": ["bigquery"],
    "Kafka": ["kafka"],
    "RabbitMQ": ["rabbitmq"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "Google Cloud": ["gcp", "google cloud"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "Ansible": ["ansible"],
    "Helm": ["helm"],
    "Linux": ["linux", "ubuntu", "debian", "centos"],
    "Nginx": ["nginx"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous delivery"],
    "GitHub Actions": ["github actions"],
    "GitLab CI": ["gitlab ci", "gitlab-ci"],
    "Jenkins": ["jenkins"],
    "Git": ["git", "github", "gitlab", "bitbucket"],
    "Prometheus": ["prometheus"],
    "Grafana": ["grafana"],
    "Datadog": ["datadog"],
    "Sentry": ["sentry"],
    "OpenTelemetry": ["opentelemetry", "otel"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow"],
    "Machine Learning": ["machine learning"],
    "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"],
    "LLMs": ["llm", "llms", "large language model", "large language models"],
    "Computer Vision": ["computer vision"],
    "Airflow": ["airflow"],
    "dbt": ["dbt"],
    "Spark": ["apache spark", "pyspark", "spark"],
    "ETL": ["etl", "elt"],
    "Data Modelling": ["data modelling", "data modeling"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Excel": ["excel"],
    "Selenium": ["selenium"],
    "Playwright": ["playwright"],
    "Cypress": ["cypress"],
    "Jest": ["jest"],
    "pytest": ["pytest"],
    "Unit Testing": ["unit testing", "unit tests"],
    "TDD": ["tdd", "test driven development", "test-driven development"],
    "Agile": ["agile", "scrum", "kanban"],
    "Jira": ["jira"],
    "Confluence": ["confluence"],
    "Figma": ["figma"],
    "UI/UX": ["ui/ux", "ux design", "ui design"],
    "Accessibility": ["accessibility", "wcag", "a11y"],
    "SEO": ["seo", "search engine optimisation", "search engine optimization"],
    "Product Management": ["product management", "product owner"],
    "Project Management": ["project management", "pmp", "prince2"],
    "Stakeholder Management": ["stakeholder management"],
    "Technical Writing": ["technical writing", "documentation"],
    "Microservices": ["microservices", "microservice"],
    "Event-Driven Architecture": ["event driven", "event-driven"],
    "System Design": ["system design", "software architecture"],
    "Distributed Systems": ["distributed systems"],
    "Performance Optimisation": ["performance optimisation", "performance optimization"],
    "Security": ["application security", "appsec", "owasp", "penetration testing"],
    "OAuth": ["oauth", "oauth2", "openid connect", "oidc"],
    "JWT": ["jwt", "json web token"],
    "Payments": ["stripe", "paypal", "payment gateway"],
    "Salesforce": ["salesforce"],
    "SAP": ["sap"],
    "Customer Support": ["customer support", "customer service"],
    "Sales": ["b2b sales", "account executive", "business development"],
    "Marketing": ["digital marketing", "content marketing", "growth marketing"],
    "Copywriting": ["copywriting"],
    "Recruiting": ["recruiting", "talent acquisition"],
    "Bookkeeping": ["bookkeeping", "accounts payable", "accounts receivable"],
    "Financial Modelling": ["financial modelling", "financial modeling"],
    "Teaching": ["teaching", "tutoring", "lecturing"],
    "Nursing": ["nursing", "registered nurse"],
    "Warehouse Operations": ["warehouse", "forklift", "picking and packing"],
    "Driving": ["cdl", "hgv", "delivery driver"],
}

SENIORITY_HINTS = {
    "principal": ["principal", "distinguished", "fellow"],
    "lead": ["lead", "staff engineer", "head of", "engineering manager", "team lead"],
    "senior": ["senior", "sr.", "snr"],
    "mid": ["mid-level", "midlevel", "intermediate"],
    "junior": ["junior", "jr.", "entry level", "entry-level", "graduate", "trainee"],
    "intern": ["intern", "internship", "placement student"],
}


def _compile(aliases):
    patterns = {}
    for canonical, alias_list in aliases.items():
        escaped = sorted((re.escape(alias) for alias in alias_list), key=len, reverse=True)
        # Alias edges are often punctuation (c#, next.js), where \b does not fire,
        # so require a non-word-ish neighbour instead of a word boundary.
        patterns[canonical] = re.compile(
            r"(?<![\w#+.])(?:" + "|".join(escaped) + r")(?![\w#+])", re.IGNORECASE
        )
    return patterns


SKILL_PATTERNS = _compile(SKILL_ALIASES)


def find_skills(text, *, limit=None):
    """Return canonical skill names that appear in the text, CV order preserved."""
    if not text:
        return []
    hits = []
    for canonical, pattern in SKILL_PATTERNS.items():
        match = pattern.search(text)
        if match:
            hits.append((match.start(), canonical))
    hits.sort()
    names = [canonical for _, canonical in hits]
    return names[:limit] if limit else names


SENIORITY_PATTERNS = _compile(SENIORITY_HINTS)


def canonical_skills(values):
    """Map free-text skills onto vocabulary names, keeping unknown ones as written.

    The LLM writes "Postgres 14" where the vocabulary says "PostgreSQL". Without
    this, a CV skill and the identical job requirement would never compare equal.
    """
    result = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        matches = find_skills(text)
        names = matches if matches else [text]
        for name in names:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                result.append(name)
    return result


def guess_seniority(text):
    """Most senior hint wins, since a CV mentioning both is usually the senior one."""
    if not text:
        return "unknown"
    for level, pattern in SENIORITY_PATTERNS.items():
        if pattern.search(text):
            return level
    return "unknown"
