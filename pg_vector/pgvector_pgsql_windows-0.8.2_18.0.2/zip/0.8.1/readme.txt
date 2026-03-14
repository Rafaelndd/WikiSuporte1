- ONLY for PostgreSQL v18 - Windows x64
- Extract the zip file to your Postgres installed folder, on overwrite dialog option, choose "Yes to all"
- Run query: 
CREATE EXTENSION vector

- Run this query to check if the extension is enable (t):
SELECT extname,extrelocatable,extversion FROM pg_extension where extname='vector'


https://github.com/andreiramani/pgvector_pgsql_windows