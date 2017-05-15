with my_table_1 as (
  select *
  from table_1
),
my_table_2 as (
  select *
  from table_2 t2
  join my_table_1 t1
  on t1.id = t2.id
)
select *
from my_table_1 t1
join my_table_2 t2
on t1.id = t2.id
;