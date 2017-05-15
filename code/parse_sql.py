from argparse import ArgumentParser
import re
from collections import defaultdict
import networkx as nx


KEY_WORDS = ['where', 'on', 'group', 'order', 'limit', 'cross', 'join']
MAX_ITERATIONS = 100

class WithStatementParser(object):
    """Parse a SQL query containing WITH statements and return the
    equivalent nested query.

    Parameters
    ----------
    filename: string, .sql file containing a query
    """

    def __init__(self, filename):
        self.filename = filename
        self.query_lines = self.load_sql_query_from_file()
        self.reset_class_vars()
        self.alias_index = 1

    def reset_class_vars(self):
        """Reset class variables to default values."""

        self.num_open_parens = 0
        self.num_close_parens = 0
        self.end_with_statement = False

    def load_sql_query_from_file(self):
        """Load a query string for a .sql text file."""

        with open(self.filename, 'r') as f:
            return f.readlines()

    def remove_excess_whitespace(self, text):
        return re.sub('\s+', ' ', text.strip())

    def remove_comments(self, text):
        """Remove all SQL comments, i.e. all text after '--'."""

        return re.sub('(.*?)--.*', '\\1', text)

    def cross_joins(self, query):
        """Replace shorthand ',' with 'cross join'."""

        # match from or join, space, any text, optional ' as ', optional text,
        # comma, optional space, any text, either space or line end
        rx = r'((?:from|join)\s+(?:.*?)(?:\s+as\s+)?(?:.*?)),(?:\s+)?((?:.*?)(?:\s|$))'

        for i in xrange(MAX_ITERATIONS):
            if re.findall(rx, query):
                query = re.sub(rx, r'\1 cross join \2', query)
            else:
                break

        return query

    def clean_original_query(self):
        """Clean text from query read from file.

        Uses self.query_lines which is an array of strings. For each line we remove
        excess whitespace, comments, blank lines, and 'with '.
        """

        new_lines = []
        for line in self.query_lines:
            line = self.remove_excess_whitespace(line).lower()
            line = self.remove_comments(line)

            # discard blank lines
            if len(line) == 0:
                continue

            # remove with when line begins 'with '
            new_lines.append(re.sub('^with(\s|$)', '', line))

        # move lines with only a single comma ',' to the previous line
        query = '\n'.join(new_lines).replace('\n,\n', ',\n')
        return self.cross_joins(query)

    def extract_with_statements(self):
        """Return a dictionary mapping {'with_statement_name' : 'with statement_query'}.

        Parameters
        ----------
        query: string, containing a SQL query
        """

        query = self.clean_original_query()

        self.with_statements = {}
        # build WITH statements in their constructed order
        self.build_order = []
        running_char_total, current_with, current_with_name = '', '', ''
        found_open_paren = False

        # match optional comma or space, any text, ' as', optional space, '('
        rx = r'[,\s]?(.*?) as ?\('
        for i, char in enumerate(query):
            running_char_total += char
            if found_open_paren:
                current_with += char
                if char in ['(', ')']:
                    self.parenthesis_tracking(char)
            else:
                if (char == '(') and (re.findall(rx, running_char_total)):
                    # found the opening parenthesis of the WITH statment
                    self.parenthesis_tracking(char)
                    current_with_name = re.sub(rx, r'\1', running_char_total)
                    found_open_paren = True
                    running_char_total = ''

            if self.end_with_statement:
                # found the end of a single WITH statement
                name = current_with_name.replace(',', '').strip()
                self.with_statements[name] = current_with[: -1].strip() # remove trailing ')'
                self.build_order.append(name)

                self.reset_class_vars()
                running_char_total, current_with, current_with_name = '', '', ''
                found_open_paren = False

        # guaranteed to be unique
        self.overall_name = '_'.join(self.build_order)
        self.build_order.append(self.overall_name)

        # the remaining characters make up the non WITH statement portion of the query
        self.with_statements[self.overall_name] = running_char_total

    def parenthesis_tracking(self, char):
        """Record keeping for open / close parenthesis. self.end_with_statement becomes
        True when the open / close parenthesis counts are equal and greater than zero.

        Parameters
        ----------
        char: string, a single character
        """

        if char == '(':
            self.num_open_parens += 1
        elif char == ')':
            self.num_close_parens += 1

        if self.num_open_parens == self.num_close_parens:
            if self.num_open_parens > 0:
                self.end_with_statement = True
                return

    def dependency_alias(self):
        """Construct dependencies and aliases from the WITH statements."""
        self.dependencies = {}
        self.aliases = {}
        self.all_aliases = set()

        with_statement_tables = self.with_statements.keys()
        for name, query in self.with_statements.iteritems():

            # extract and save all table names from a WITH statement query
            # regex matches from or join, space, any text, then space or end line
            tables = re.findall(r'(?:from|join)(?:\s+)(.*?)(?:\s+|$)', query)
            self.dependencies[name] = [t for t in tables if t in with_statement_tables]

            # extract all alias for tables in a WITH statement query
            # regex matches from or join, space, any text, space, optional 'as ', any text, then space or end line
            alias = re.findall(r'(?:from|join)(?:\s+)(.*?)(?:\s+)(?:as\s+)?(.*?)(?:\s+|$)', query)
            tmp_aliases = {}
            for t, a in alias:
                # only keep WITH statement table name
                if t in with_statement_tables:
                    # when no alias exists we'll typically match a SQL key word, which we skip
                    if a not in KEY_WORDS:
                        tmp_aliases[t] = a
                        # keep unique set of all extracted aliases
                        self.all_aliases.add(a)
            self.aliases[name] = tmp_aliases

    def dependency_graph_contains_cycles(self):
        """Return True is the dependency graph contrains a loop, False otherwise.

        Example cycles
        --------------
            - A depends on B and B depends on A
            - A depends on B, B depends on C, and C depends on A
        """

        # Directed graph
        G = nx.DiGraph()
        for k, arr in self.dependencies.iteritems():
            if len(arr) == 0: continue

            for a in arr:
                G.add_edge(k, a)

        # check for cycles
        return bool(list(nx.simple_cycles(G)))

    def get_alias(self, with_table, nested_table):
        """Return the alias of the nested table. If no alias defined in the query
        we create a new unique alias, otherwise return the alias from the query.

        Parameters
        ----------
        with_table: string, the name of a WITH statement table
        nested_table: string, the name of a table inside a WITH statement query

        Example
        -------
        WITH with_table as (
            select *
            from nested_table
        )
        """

        aliases_in_with_statement = self.aliases[with_table]
        if nested_table in aliases_in_with_statement:
            # table has an aliaas
            return ''
        else:
            # create a new unique alias
            return self.next_alias()

    def next_alias(self):
        """Return the next unique alias, following the pattern: t1, t2, t3, ..."""

        a = 't{0}'.format(self.alias_index)
        self.alias_index += 1

        if a in self.all_aliases:
            # current alias is already used in the query
            return self.next_alias()
        else:
            return ' ' + a

    def create_nested_with_statements(self):
        """Replace WITH statement table names with their actual queries."""

        self.dependency_alias()

        if self.dependency_graph_contains_cycles():
            raise Exception('Query dependence structure contains a cycle.')
        else:
            for table in self.build_order:
                # replace WITH statement table name with this query
                update_query = self.with_statements[table]

                # these table names occur in update_query
                table_dependencies = self.dependencies[table]
                for d in table_dependencies:
                    # get and format the nested query
                    nested_query = '(\n{0}\n)'.format(self.with_statements[d])

                    # append an alias
                    nested_query += self.get_alias(table, d)

                    # replace first occurrence only (for self joins)
                    update_query = re.sub(d, nested_query.replace('\n', '\n  '), update_query, 1)

                # replace original query with the nested version
                self.with_statements[table] = update_query

    def save_output(self, query):
        """Save the query string to a file. The output filename add the suffix '_nested'
        to the input filename.

        Parameters
        ----------
        query: string, a SQL query

        Example
        -------
            input filename: my_query.sql
            output filename: my_query_nested.sql
        """

        output_file = re.sub(r'(.*?)(\.sql)', r'\1_nested\2', self.filename)
        with open(output_file, 'w') as f:
            f.write(query)

    def get_nested_query(self):
        """Return output nested query."""

        return self.with_statements[self.overall_name].strip()

    def create_nested_query(self, print_query=True):
        """Main method. Executes all class methods and saves the nested query to disk."""

        self.extract_with_statements()
        self.create_nested_with_statements()

        nested_query = self.get_nested_query()
        self.save_output(nested_query)

        if print_query:
            print nested_query

if __name__ == '__main__':

    parser = ArgumentParser()
    parser.add_argument('--filename', nargs='?', type=str)
    args = parser.parse_args()

    sql_parser = WithStatementParser(args.filename)
    sql_parser.create_nested_query()
