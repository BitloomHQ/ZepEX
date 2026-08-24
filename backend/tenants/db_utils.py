def get_external_db_connection(config):
    """Open a connection to the company's configured external database.

    Drivers are imported lazily so Django URL loading does not pull
    psycopg2/pymysql/pyodbc/oracledb into every worker at startup.
    """
    if config.db_engine == "postgresql":
        import psycopg2

        return psycopg2.connect(
            host=config.db_host,
            port=config.db_port,
            dbname=config.db_name,
            user=config.db_user,
            password=config.db_password,
            connect_timeout=10,
        )

    if config.db_engine == "mysql":
        import pymysql

        return pymysql.connect(
            host=config.db_host,
            port=config.db_port,
            database=config.db_name,
            user=config.db_user,
            password=config.db_password,
            connect_timeout=10,
        )

    if config.db_engine == "mssql":
        import pyodbc

        return pyodbc.connect(
            (
                "DRIVER={ODBC Driver 17 for SQL Server};"
                f"SERVER={config.db_host},{config.db_port};"
                f"DATABASE={config.db_name};"
                f"UID={config.db_user};"
                f"PWD={config.db_password};"
                "TrustServerCertificate=yes;"
            ),
            timeout=10,
        )

    if config.db_engine == "oracle":
        import oracledb

        dsn = oracledb.makedsn(
            config.db_host,
            config.db_port,
            service_name=config.db_name,
        )

        return oracledb.connect(
            user=config.db_user,
            password=config.db_password,
            dsn=dsn,
        )

    raise Exception("Unsupported database engine.")
