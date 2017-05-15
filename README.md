## Overview

Using SQL WITH statements (CTEs) often result in much cleaner queries. However in PostgreSQL, CTEs are [optimisation fences](https://blog.2ndquadrant.com/postgresql-ctes-are-optimization-fences/) which can lead to worse performance. The goal of this project is to parse a query containing WITH statements and output the equivalent query using nested subqueries.

Run from the command line using

```
$ python parse_sql.py --filename query.sql
```

and the nested subquery query will be output to `query_nested.sql`. The parser requires tables be referenced via alias, i.e. using

```
SELECT
  t.col_1,
  t.col_2
FROM my_table t
```

not

```
SELECT
  my_table.col_1,
  my_table.col_2
FROM my_table
```

## Example

Input using WITH statements:

```
WITH my_table_1 AS (
  SELECT *
  FROM table_1
),
my_table_2 AS (
  SELECT *
  FROM table_2 t2
  JOIN my_table_1 t1
  ON t1.id = t2.id
)

SELECT *
FROM my_table_1 t1
JOIN my_table_2 t2
ON t1.id = t2.id
```

Output using nested subqueries:

```
select *
from (
  select *
  from table_1
  ) t1
join (
  select *
  from table_2 t2
  join (
    select *
    from table_1
    ) t1
  on t1.id = t2.id
  ) t2
on t1.id = t2.id
```