from ncs_backend.shared.db.dialect import DatabaseDialect

MYSQL_DIALECT = DatabaseDialect(name="mysql", placeholder="%s")
