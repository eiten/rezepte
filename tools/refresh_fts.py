"""Rebuild recipe FTS (fts5) table and triggers.

Use when triggers were broken or FTS is out of sync. This script drops the
FTS table and all related triggers, recreates them, and backfills all recipes
with their ingredients and steps.

Usage:
    python tools/refresh_fts.py
"""

import sqlite3
from setup_db import get_db_path


def rebuild_fts(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Drop triggers and FTS table
    cur.executescript(
        """
        DROP TRIGGER IF EXISTS recipe_fts_ai;
        DROP TRIGGER IF EXISTS recipe_fts_au;
        DROP TRIGGER IF EXISTS recipe_fts_ad;
        DROP TRIGGER IF EXISTS recipe_fts_steps_ai;
        DROP TRIGGER IF EXISTS recipe_fts_steps_au;
        DROP TRIGGER IF EXISTS recipe_fts_steps_ad;
        DROP TRIGGER IF EXISTS recipe_fts_ing_ai;
        DROP TRIGGER IF EXISTS recipe_fts_ing_au;
        DROP TRIGGER IF EXISTS recipe_fts_ing_ad;

        DROP TABLE IF EXISTS recipe_fts;
        """
    )

    # Recreate non-contentless FTS5 table
    cur.executescript(
        """
        CREATE VIRTUAL TABLE recipe_fts USING fts5(
            name,
            author,
            source,
            preamble,
            ingredients,
            steps
        );
        """
    )

    # Triggers: keep simple UPDATE/INSERT/DELETE behavior
    cur.executescript(
        """
        -- Recipes INSERT
        CREATE TRIGGER recipe_fts_ai AFTER INSERT ON recipes
        BEGIN
          INSERT INTO recipe_fts(rowid, name, author, source, preamble, ingredients, steps)
          VALUES(
            NEW.id,
            COALESCE(NEW.name, ''),
            COALESCE(NEW.author, ''),
            COALESCE(NEW.source, ''),
            COALESCE(NEW.preamble, ''),
            '',
            ''
          );
        END;

        -- Recipes UPDATE
        CREATE TRIGGER recipe_fts_au AFTER UPDATE ON recipes
        BEGIN
          UPDATE recipe_fts SET
            name = COALESCE(NEW.name, ''),
            author = COALESCE(NEW.author, ''),
            source = COALESCE(NEW.source, ''),
            preamble = COALESCE(NEW.preamble, '')
          WHERE rowid = NEW.id;
        END;

        -- Recipes DELETE
        CREATE TRIGGER recipe_fts_ad AFTER DELETE ON recipes
        BEGIN
          DELETE FROM recipe_fts WHERE rowid = OLD.id;
        END;

        -- Steps INSERT/UPDATE
        CREATE TRIGGER recipe_fts_steps_ai AFTER INSERT ON steps
        BEGIN
          UPDATE recipe_fts SET steps = 
            COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
              SELECT markdown_text FROM steps WHERE recipe_id = NEW.recipe_id ORDER BY position
            )), '')
          WHERE rowid = NEW.recipe_id;
        END;

        CREATE TRIGGER recipe_fts_steps_au AFTER UPDATE ON steps
        BEGIN
          UPDATE recipe_fts SET steps = 
            COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
              SELECT markdown_text FROM steps WHERE recipe_id = NEW.recipe_id ORDER BY position
            )), '')
          WHERE rowid = NEW.recipe_id;
        END;

        -- Steps DELETE
        CREATE TRIGGER recipe_fts_steps_ad AFTER DELETE ON steps
        BEGIN
          UPDATE recipe_fts SET steps = 
            COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
              SELECT markdown_text FROM steps WHERE recipe_id = OLD.recipe_id ORDER BY position
            )), '')
          WHERE rowid = OLD.recipe_id;
        END;

        -- Ingredients INSERT/UPDATE/DELETE
        CREATE TRIGGER recipe_fts_ing_ai AFTER INSERT ON ingredients
        BEGIN
          UPDATE recipe_fts SET ingredients = 
            COALESCE((SELECT group_concat(item || ' ' || COALESCE(note,''), ' ') FROM (
              SELECT i.item, i.note FROM ingredients i JOIN steps s ON i.step_id = s.id
              WHERE s.recipe_id = (SELECT recipe_id FROM steps WHERE id = NEW.step_id)
              ORDER BY s.position, i.position
            )), '')
          WHERE rowid = (SELECT recipe_id FROM steps WHERE id = NEW.step_id);
        END;

        CREATE TRIGGER recipe_fts_ing_au AFTER UPDATE ON ingredients
        BEGIN
          UPDATE recipe_fts SET ingredients = 
            COALESCE((SELECT group_concat(item || ' ' || COALESCE(note,''), ' ') FROM (
              SELECT i.item, i.note FROM ingredients i JOIN steps s ON i.step_id = s.id
              WHERE s.recipe_id = (SELECT recipe_id FROM steps WHERE id = NEW.step_id)
              ORDER BY s.position, i.position
            )), '')
          WHERE rowid = (SELECT recipe_id FROM steps WHERE id = NEW.step_id);
        END;

        CREATE TRIGGER recipe_fts_ing_ad AFTER DELETE ON ingredients
        BEGIN
          UPDATE recipe_fts SET ingredients = 
            COALESCE((SELECT group_concat(item || ' ' || COALESCE(note,''), ' ') FROM (
              SELECT i.item, i.note FROM ingredients i JOIN steps s ON i.step_id = s.id
              WHERE s.recipe_id = (SELECT recipe_id FROM steps WHERE id = OLD.step_id)
              ORDER BY s.position, i.position
            )), '')
          WHERE rowid = (SELECT recipe_id FROM steps WHERE id = OLD.step_id);
        END;
        """
    )

    # Backfill all recipes
    cur.executescript(
        """
        INSERT INTO recipe_fts(rowid, name, author, source, preamble, ingredients, steps)
        SELECT
          r.id,
          COALESCE(r.name, ''),
          COALESCE(r.author, ''),
          COALESCE(r.source, ''),
          COALESCE(r.preamble, ''),
          COALESCE((SELECT group_concat(item || ' ' || COALESCE(note,''), ' ') FROM (
            SELECT i.item, i.note FROM ingredients i JOIN steps s ON i.step_id = s.id
            WHERE s.recipe_id = r.id ORDER BY s.position, i.position
          )), ''),
          COALESCE((SELECT group_concat(markdown_text, ' ') FROM (
            SELECT markdown_text FROM steps WHERE recipe_id = r.id ORDER BY position
          )), '')
        FROM recipes r;
        """
    )

    conn.commit()


def main() -> None:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        rebuild_fts(conn)
        print(f"FTS rebuilt successfully for: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
