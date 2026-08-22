package org.telegram.nersiti;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

/**
 * Локальный архив на телефоне (SQLite). Зеркало схемы бэкенда (PLAN.md §5),
 * плюс поле synced для очереди выгрузки на ПК.
 */
public class NersitiStore extends SQLiteOpenHelper {

    private static final String DB = "nersiti_archive.db";
    private static final int VERSION = 1;

    public NersitiStore(Context ctx) {
        super(ctx, DB, null, VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS messages(" +
            "id INTEGER PRIMARY KEY AUTOINCREMENT," +
            "tg_message_id INTEGER, chat_id INTEGER, sender_id INTEGER," +
            "sender_name TEXT, text TEXT, date INTEGER, reply_to INTEGER," +
            "is_outgoing INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0," +
            "edited_at INTEGER DEFAULT 0, media_path TEXT," +
            "was_disappearing INTEGER DEFAULT 0, self_destruct INTEGER DEFAULT 0," +
            "is_secret INTEGER DEFAULT 0, ttl INTEGER DEFAULT 0," +
            "synced INTEGER DEFAULT 0);");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_chat_date ON messages(chat_id, date);");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldV, int newV) {
        // миграции по мере роста версии
    }

    /** Сохранить сообщение (в т.ч. исчезающее/секретное). Возвращает rowid. */
    public long saveMessage(long tgId, long chatId, long senderId, String senderName,
                            String text, long date, long replyTo, int outgoing,
                            String mediaPath, int wasDisappearing, int selfDestruct,
                            int isSecret, int ttl) {
        SQLiteDatabase db = getWritableDatabase();
        ContentValues v = new ContentValues();
        v.put("tg_message_id", tgId);
        v.put("chat_id", chatId);
        v.put("sender_id", senderId);
        v.put("sender_name", senderName);
        v.put("text", text);
        v.put("date", date);
        v.put("reply_to", replyTo);
        v.put("is_outgoing", outgoing);
        v.put("media_path", mediaPath);
        v.put("was_disappearing", wasDisappearing);
        v.put("self_destruct", selfDestruct);
        v.put("is_secret", isSecret);
        v.put("ttl", ttl);
        v.put("synced", 0);
        return db.insert("messages", null, v);
    }

    public void markDeleted(long chatId, long tgId) {
        getWritableDatabase().execSQL(
            "UPDATE messages SET is_deleted=1, synced=0 WHERE chat_id=? AND tg_message_id=?",
            new Object[]{chatId, tgId});
    }

    public void markSynced(long rowId) {
        getWritableDatabase().execSQL("UPDATE messages SET synced=1 WHERE id=?",
            new Object[]{rowId});
    }

    /** Курсор по несинхронизированным сообщениям (для выгрузки на ПК). */
    public Cursor unsynced(int limit) {
        return getReadableDatabase().rawQuery(
            "SELECT * FROM messages WHERE synced=0 ORDER BY id ASC LIMIT ?",
            new String[]{String.valueOf(limit)});
    }

    /** Полный архив чата (для экрана «Архив чата»). */
    public Cursor chatHistory(long chatId, int limit, int offset) {
        return getReadableDatabase().rawQuery(
            "SELECT * FROM messages WHERE chat_id=? ORDER BY date ASC, id ASC " +
            "LIMIT ? OFFSET ?",
            new String[]{String.valueOf(chatId), String.valueOf(limit),
                         String.valueOf(offset)});
    }
}
