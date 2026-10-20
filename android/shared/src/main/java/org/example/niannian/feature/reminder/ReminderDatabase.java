package org.example.niannian.feature.reminder;

import androidx.annotation.NonNull;
import androidx.room.Database;
import androidx.room.Dao;
import androidx.room.Entity;
import androidx.room.Insert;
import androidx.room.OnConflictStrategy;
import androidx.room.PrimaryKey;
import androidx.room.Query;
import androidx.room.RoomDatabase;

/** One encrypted active-family snapshot: cache and PendingActions commit together. */
@Database(entities = {ReminderDatabase.Snapshot.class}, version = 1, exportSchema = true)
public abstract class ReminderDatabase extends RoomDatabase {
    public abstract SnapshotDao snapshots();

    @Entity(tableName = "reminder_snapshot")
    public static class Snapshot {
        @PrimaryKey public int id = 1;
        @NonNull public byte[] encrypted = new byte[0];
    }

    @Dao
    public interface SnapshotDao {
        @Query("SELECT * FROM reminder_snapshot WHERE id = 1") Snapshot load();
        @Insert(onConflict = OnConflictStrategy.REPLACE) void save(Snapshot snapshot);
        @Query("DELETE FROM reminder_snapshot") void clear();
    }
}
