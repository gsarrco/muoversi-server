"""Convert stop_times to partitioned table

Revision ID: d55702afa188
Revises: 1f2c7b1eec8b
Create Date: 2023-10-29 16:09:44.815425

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd55702afa188'
down_revision = '7c12f6bfe3c6'
branch_labels = None
depends_on = None


# Define the migration
def upgrade():
    # remove foreign key "stop_times_stop_id_fkey"
    op.drop_constraint('stop_times_stop_id_fkey', 'stop_times', type_='foreignkey')

    # rename table "stop_times" to "stop_times_reg"
    op.rename_table('stop_times', 'stop_times_reg')

    # create the partitioned table "stop_times" for field "orig_dep_date"
    op.execute("""
        CREATE TABLE stop_times (
            id SERIAL NOT NULL,
            stop_id character varying NOT NULL,
            sched_arr_dt timestamp without time zone,
            sched_dep_dt timestamp without time zone,
            platform character varying,
            orig_dep_date date NOT NULL,
            orig_id character varying NOT NULL,
            dest_text character varying NOT NULL,
            number integer NOT NULL,
            route_name character varying NOT NULL,
            source character varying,
            CONSTRAINT stop_times_stop_id_fkey FOREIGN key(stop_id) REFERENCES stops(id)
        ) PARTITION BY RANGE (orig_dep_date);
        CREATE UNIQUE INDEX stop_times_unique_idx ON stop_times(stop_id, number, source, orig_dep_date);
    """)


def downgrade():
    # drop the partitioned table "stop_times"
    op.drop_table('stop_times')

    # rename table "stop_times_reg" to "stop_times"
    op.rename_table('stop_times_reg', 'stop_times')

    # add foreign key "stop_times_stop_id_fkey"
    op.create_foreign_key('stop_times_stop_id_fkey', 'stop_times', 'stops', ['stop_id'], ['id'])
