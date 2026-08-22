package org.telegram.nersiti;

import android.content.Context;

/**
 * Фасад моста Nersiti. В него форк отдаёт события, он складывает в локальный
 * архив и выгружает на бэкенд-ПК. Это единственная точка, которую нужно
 * ВЫЗЫВАТЬ из кода форка — так правки ядра минимальны.
 *
 * ТОЧКИ ИНТЕГРАЦИИ В ФОРК (см. docs/BUILD_APK.md):
 *  1) при получении/отправке сообщения          -> onMessage(...)
 *  2) при получении исчезающего/one-time медиа   -> onDisappearingMedia(...)
 *  3) при расшифровке секретного (E2E) сообщения -> onSecretMessage(...)
 *  4) при удалении сообщения собеседником        -> onDeleted(...)
 *  5) кнопка «Архив чата» / панель черновика     -> requestReply(...)
 */
public class NersitiBridge {

    private static NersitiStore store;

    public static void init(Context ctx) {
        if (store == null) store = new NersitiStore(ctx.getApplicationContext());
    }

    /** Обычное сообщение (входящее/исходящее). */
    public static void onMessage(long tgId, long chatId, long senderId,
                                 String senderName, String text, long date,
                                 long replyTo, boolean outgoing, String mediaPath) {
        long row = store.saveMessage(tgId, chatId, senderId, senderName, text, date,
                replyTo, outgoing ? 1 : 0, mediaPath, 0, 0, 0, 0);
        pushAsync(row);
    }

    /** Исчезающее / «просмотр один раз» / самоуничтожающееся медиа. */
    public static void onDisappearingMedia(long tgId, long chatId, long senderId,
                                           String senderName, String savedPath,
                                           boolean selfDestruct) {
        if (!NersitiConfig.SAVE_DISAPPEARING) return;
        long row = store.saveMessage(tgId, chatId, senderId, senderName, "",
                System.currentTimeMillis() / 1000, 0, 0, savedPath,
                1, selfDestruct ? 1 : 0, 0, 0);
        pushAsync(row);
    }

    /** Сообщение из секретного (E2E) чата — уже расшифрованное форком. */
    public static void onSecretMessage(long tgId, long chatId, long senderId,
                                       String senderName, String text,
                                       String savedPath, int ttl) {
        if (!NersitiConfig.SAVE_SECRET_CHATS) return;
        long row = store.saveMessage(tgId, chatId, senderId, senderName, text,
                System.currentTimeMillis() / 1000, 0, 0, savedPath,
                savedPath != null ? 1 : 0, 0, 1, ttl);
        pushAsync(row);
    }

    /** Собеседник удалил сообщение — оставляем копию с пометкой. */
    public static void onDeleted(long chatId, long tgId) {
        if (!NersitiConfig.SAVE_DELETED) return;
        store.markDeleted(chatId, tgId);
    }

    /** Запрос ответа у мозга (для панели черновика / авто-режима). */
    public static String requestReply(long chatId, String incomingText) {
        try {
            return NersitiSync.requestReply(chatId, incomingText);
        } catch (Exception e) {
            return "{\"action\":\"none\",\"reason\":\"backend_unavailable\"}";
        }
    }

    public static NersitiStore store() { return store; }

    // Выгрузка на ПК в фоне (упрощённо — по одной строке; в проде батчить).
    private static void pushAsync(final long row) {
        new Thread(new Runnable() {
            @Override public void run() {
                // TODO(исполнитель): собрать JSON из строки row и вызвать
                // NersitiSync.syncMessages(json); при успехе store.markSynced(row).
                // Здесь оставлен каркас, чтобы минимизировать правки ядра форка.
            }
        }).start();
    }
}
