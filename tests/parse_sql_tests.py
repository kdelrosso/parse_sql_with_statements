import sys
from os import path
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))) + '/code')

from unittest import TestCase, main
from parse_sql import WithStatementParser

class ParseSqlTests(TestCase):

    def test_helper_cleaning_methods(self):
        sql_parser = WithStatementParser('./test_data/example_1.sql')

        input_text = ' extra\n space  everywhere '
        output_text = 'extra space everywhere'
        self.assertEqual(sql_parser.remove_excess_whitespace(input_text), output_text)

        input_text = '-- comment\nselect * from table;'
        output_text = '\nselect * from table;'
        self.assertEqual(sql_parser.remove_comments(input_text), output_text)

        input_text = 'select * -- inline comment\nfrom table;'
        output_text = 'select * \nfrom table;'
        self.assertEqual(sql_parser.remove_comments(input_text), output_text)

        input_text = 'select * from table1, table2;'
        output_text = 'select * from table1 cross join table2;'
        self.assertEqual(sql_parser.cross_joins(input_text), output_text)

        input_text = 'select * from table1 t1, table2 t2;'
        output_text = 'select * from table1 t1 cross join table2 t2;'
        self.assertEqual(sql_parser.cross_joins(input_text), output_text)

        input_text = 'select * from table1 as t1, table2 as t2;'
        output_text = 'select * from table1 as t1 cross join table2 as t2;'
        self.assertEqual(sql_parser.cross_joins(input_text), output_text)

        input_text = 'select * from table1, table2, table3;'
        output_text = 'select * from table1 cross join table2 cross join table3;'
        self.assertEqual(sql_parser.cross_joins(input_text), output_text)

        output_text = 'my_table_1 as (\nselect *\nfrom table_1\n)\nselect *\nfrom my_table_1\n;'
        self.assertEqual(sql_parser.clean_original_query(), output_text)

    def test_parenthesis_tracking(self):
        sql_parser = WithStatementParser('./test_data/example_1.sql')

        self.assertFalse(sql_parser.end_with_statement)

        sql_parser.parenthesis_tracking('(')
        self.assertEqual(sql_parser.num_open_parens, 1)

        self.assertFalse(sql_parser.end_with_statement)

        sql_parser.parenthesis_tracking(')')
        self.assertEqual(sql_parser.num_close_parens, 1)

        self.assertTrue(sql_parser.end_with_statement)

    def test_extract_with_statements(self):
        sql_parser = WithStatementParser('./test_data/example_2.sql')
        sql_parser.extract_with_statements()

        self.assertEqual(sql_parser.overall_name, 'my_table_1_my_table_2')
        self.assertEqual(sql_parser.build_order, ['my_table_1', 'my_table_2', 'my_table_1_my_table_2'])
        self.assertEqual(sorted(sql_parser.with_statements.keys()), ['my_table_1', 'my_table_1_my_table_2', 'my_table_2'])
        self.assertEqual(sql_parser.with_statements['my_table_1'], 'select *\nfrom table_1')
        self.assertEqual(sql_parser.with_statements['my_table_2'], 'select *\nfrom table_2')
        self.assertEqual(sql_parser.with_statements['my_table_1_my_table_2'], '\nselect *\nfrom my_table_1 t1\njoin my_table_2 t2\non t1.id = t2.id\n;')

    def test_dependency(self):
        sql_parser = WithStatementParser('./test_data/example_3.sql')

        sql_parser.with_statements = {
            'my_table_1': 'select *\nfrom table_1',
            'my_table_2': 'select *\nfrom my_table_1 as m',
            'my_table_1_my_table_2': '\nselect *\nfrom my_table_1 t1\njoin my_table_2 t2\non t1.id = t2.id\n;'
            }
        sql_parser.dependency_alias()

        self.assertEqual(sql_parser.dependencies['my_table_1'], [])
        self.assertEqual(sql_parser.dependencies['my_table_2'], ['my_table_1'])
        self.assertEqual(sql_parser.dependencies['my_table_1_my_table_2'], ['my_table_1', 'my_table_2'])

        # no cycle in dependence
        sql_parser.dependencies = {
            'my_table_1': [],
            'my_table_2': ['my_table_1']
            }
        self.assertFalse(sql_parser.dependency_graph_contains_cycles())

        # 2 node cycle in dependence
        sql_parser.dependencies = {
            'my_table_1': ['my_table_2'],
            'my_table_2': ['my_table_1']
            }
        self.assertTrue(sql_parser.dependency_graph_contains_cycles())

        # 3 node cycle in dependence
        sql_parser.dependencies = {
            'my_table_1': ['my_table_2'],
            'my_table_2': ['my_table_3'],
            'my_table_3': ['my_table_1']
            }
        self.assertTrue(sql_parser.dependency_graph_contains_cycles())

    def test_alias(self):
        sql_parser = WithStatementParser('./test_data/example_3.sql')

        sql_parser.with_statements = {
            'my_table_1': 'select *\nfrom table_1',
            'my_table_2': 'select *\nfrom my_table_1 as m',
            'my_table_1_my_table_2': '\nselect *\nfrom my_table_1 t1\njoin my_table_2 t2\non t1.id = t2.id\n;'
            }
        sql_parser.dependency_alias()

        self.assertEqual(sorted(sql_parser.all_aliases), ['m', 't1', 't2'])

        self.assertEqual(sql_parser.aliases['my_table_1'], {})
        self.assertEqual(sql_parser.aliases['my_table_2'], {'my_table_1': 'm'})
        self.assertEqual(sql_parser.aliases['my_table_1_my_table_2']['my_table_1'], 't1')
        self.assertEqual(sql_parser.aliases['my_table_1_my_table_2']['my_table_2'], 't2')

        # return empty string when alias exists
        sql_parser.aliases = {'my_table_2': {'my_table_1', 't1'}}
        self.assertEqual(sql_parser.get_alias('my_table_2', 'my_table_1'), '')

        # return next available alias when alias doesn't exist
        sql_parser.alias_index = 1
        sql_parser.all_aliases = ['t1']
        self.assertEqual(sql_parser.get_alias('my_table_2', 'my_table_3'), ' t2')

        # return next available alias
        sql_parser.alias_index = 1
        sql_parser.all_aliases = ['t1', 't2']
        self.assertEqual(sql_parser.next_alias(), ' t3')

    def test_create_nested_with_statements(self):
        sql_parser = WithStatementParser('./test_data/example_3.sql')
        sql_parser.extract_with_statements()
        sql_parser.create_nested_with_statements()

        nested_query = '''
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
;
'''.strip()

        self.assertEqual(sql_parser.get_nested_query(), nested_query)

if __name__ == '__main__':
    main()
