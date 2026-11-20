"""scene details: frame range, references, characters, location, prompt versions, manual status override

Revision ID: e4a1b2c3d560
Revises: d3f0a1b2c459
Create Date: 2026-11-20 08:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e4a1b2c3d560'
down_revision: Union[str, None] = 'd3f0a1b2c459'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    for table, uq in (('project_characters', 'uq_project_character_name'),
                      ('project_locations', 'uq_project_location_name')):
        op.create_table(
            table,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(length=120), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('project_id', 'name', name=uq),
        )
        op.create_index(f'ix_{table}_project_id', table, ['project_id'])

    op.add_column('scenes', sa.Column('status_override', sa.String(length=20), nullable=True))
    op.add_column('scenes', sa.Column('duration_sec', sa.Float(), nullable=True))
    op.add_column('scenes', sa.Column('frame_in', sa.Integer(), nullable=True))
    op.add_column('scenes', sa.Column('frame_out', sa.Integer(), nullable=True))
    op.add_column('scenes', sa.Column('fps', sa.Float(), nullable=True))
    op.add_column('scenes', sa.Column('reference_links', JSON, nullable=False, server_default=sa.text("'[]'")))
    op.add_column('scenes', sa.Column('location_id', sa.Integer(), nullable=True))
    op.create_index('ix_scenes_location_id', 'scenes', ['location_id'])
    op.create_foreign_key('fk_scenes_location_id_project_locations', 'scenes', 'project_locations',
                          ['location_id'], ['id'], ondelete='SET NULL')

    op.create_table(
        'scene_characters',
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('scenes.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('character_id', sa.Integer(), sa.ForeignKey('project_characters.id', ondelete='CASCADE'),
                  primary_key=True),
    )
    op.create_table(
        'scene_prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('scenes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('tool', sa.String(length=80), nullable=True),
        sa.Column('seed', sa.String(length=80), nullable=True),
        sa.Column('settings', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scene_id', 'version', name='uq_scene_prompt_version'),
    )
    op.create_index('ix_scene_prompts_scene_id', 'scene_prompts', ['scene_id'])
    for t in ('project_characters', 'project_locations', 'scene_characters', 'scene_prompts'):
        op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY')  # see 0005


def downgrade() -> None:
    op.drop_index('ix_scene_prompts_scene_id', table_name='scene_prompts')
    op.drop_table('scene_prompts')
    op.drop_table('scene_characters')
    op.drop_constraint('fk_scenes_location_id_project_locations', 'scenes', type_='foreignkey')
    op.drop_index('ix_scenes_location_id', table_name='scenes')
    for col in ('location_id', 'reference_links', 'fps', 'frame_out', 'frame_in', 'duration_sec', 'status_override'):
        op.drop_column('scenes', col)
    for table in ('project_locations', 'project_characters'):
        op.drop_index(f'ix_{table}_project_id', table_name=table)
        op.drop_table(table)
