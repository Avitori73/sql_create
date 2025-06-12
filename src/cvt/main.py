from sqlglot import parse, parse_one, exp
from rich.prompt import Prompt
import pyperclip


def parse_one_or_multi(sql):
    """
    Parse SQL statements, returning a list of parsed objects.
    """
    parsed = parse(sql, read="postgres")
    return parsed


def is_create_ddl(sql):
    """
    Check if the SQL statement is a CREATE TABLE DDL statement.
    """
    parsed = parse_one(sql, read="postgres")
    if parsed and parsed.kind == "TABLE":
        return True
    return False


def convert_table(parsed):
    """
    Convert the parsed primary key to a constraint.
    """
    if not is_table(parsed):
        raise ValueError("Parsed object is not a table")

    is_partition = False
    primary_key = []
    for column in parsed.find_all(exp.ColumnDef):
        if is_primary_key(column):
            # Remove the primary key constraint from the column
            remove_primary_key_constraints(column)
            primary_key.append(column.name)
        if column.name == "dealer_partition_":
            is_partition = True
            primary_key.append(column.name)

    if primary_key:
        add_primary_key_constraint(parsed, primary_key)

    if is_partition:
        add_partition(parsed)
        # Create partition tables, prompting the user for the number of partitions, default is 5
        count = Prompt.ask("Enter the number of partitions (default is 5)", default=5)
        try:
            count = int(count)
        except ValueError:
            count = 5
        partition_cnt = count
        partitions = create_partition_table(parsed, partition_cnt)
        return [parsed, *partitions]
    return [parsed]


def is_table(parsed):
    """
    Check if the parsed object is a table.
    """
    if parsed and parsed.kind == "TABLE":
        return True
    return False


def create_partition_table(parsed, partition_cnt):
    """
    Create partition tables based on the parsed table.
    """
    tablename = parsed.find(exp.Table).name
    partitions = []
    for i in range(1, partition_cnt + 1):
        partition_name = f"{tablename}_batch{i:02d}"
        partition = exp.Create(
            this=exp.Table(this=exp.Identifier(this=partition_name, quoted=False)),
            kind="TABLE",
            properties=exp.Properties(
                expressions=[
                    exp.PartitionedOfProperty(
                        this=exp.Table(
                            this=exp.Identifier(this=tablename, quoted=False),
                        ),
                        expression=exp.PartitionBoundSpec(
                            this=[exp.Literal(this=f"{i:02d}", is_string=True)]
                        ),
                    )
                ]
            ),
        )
        partitions.append(partition)
    return partitions


def add_primary_key_constraint(parsed, primary_key):
    """
    Add a primary key constraint to the table.
    """
    tablename = parsed.find(exp.Table).name
    pk_constraint_name = f"pk_{tablename}"
    pk_constraint = exp.Constraint(
        this=exp.Identifier(this=pk_constraint_name, quoted=False),
        expressions=[
            exp.PrimaryKey(
                expressions=[
                    exp.Ordered(
                        this=exp.Column(this=exp.Identifier(this=col, quoted=False)),
                        nulls_first=False,
                    )
                    for col in primary_key
                ]
            )
        ],
    )
    parsed.find(exp.Schema).expressions.append(pk_constraint)


def add_partition(parsed):
    """
    Add partitioning to the table.
    """
    properties = exp.Properties(
        expressions=[
            exp.PartitionedByProperty(
                this=exp.List(
                    expressions=[
                        exp.Column(
                            this=exp.Identifier(this="dealer_partition_", quoted=False)
                        )
                    ]
                )
            )
        ]
    )
    parsed.set("properties", properties)


def is_primary_key(column):
    """
    Check if the column is a primary key.
    """
    if column.find(exp.PrimaryKeyColumnConstraint):
        return True
    return False


def remove_primary_key_constraints(column):
    """
    Remove the primary key constraint from column.
    """
    for constraint in column.constraints:
        if isinstance(constraint.kind, exp.PrimaryKeyColumnConstraint):
            column.constraints.remove(constraint)
            break


def process_sql(sql):
    parseds = parse_one_or_multi(sql)
    results = []
    for parsed in parseds:
        try:
            convert_parsed = convert_table(parsed)
            result = (
                ";\n".join(
                    [ast.sql(dialect="postgres", pretty=True) for ast in convert_parsed]
                )
                + ";"
            )
            results.append(result)
        except Exception as e:
            continue

    return "\n\n".join(results)


def main():
    """
    Main function to process SQL statements.
    """
    try:
        sql = pyperclip.paste()
        result = process_sql(sql)
        pyperclip.copy(result)
        print("SQL statements processed and copied to clipboard.")
    except Exception as e:
        print(f"Error processing SQL statements: {e}")


if __name__ == "__main__":
    main()
