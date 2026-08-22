package org.telegram.nersiti;

/**
 * Настройки моста Nersiti (сторона телефона).
 * Заполняются при сборке / в настройках мода.
 */
public final class NersitiConfig {

    /** Адрес бэкенда-мозга на ПК (локальная сеть или Tailscale). */
    public static String BACKEND_URL = "http://192.168.1.10:8765";

    /** Общий секрет, совпадает с SYNC_TOKEN на бэкенде. */
    public static String SYNC_TOKEN = "change_me_long_random";

    /** Сохранять исчезающие / самоуничтожающиеся медиа. */
    public static boolean SAVE_DISAPPEARING = true;

    /** Сохранять содержимое секретных (E2E) чатов. */
    public static boolean SAVE_SECRET_CHATS = true;

    /** Сохранять удалённые собеседником сообщения (анти-recall). */
    public static boolean SAVE_DELETED = true;

    /** Режим автоответа по умолчанию: off | draft | auto. */
    public static String DEFAULT_MODE = "off";

    private NersitiConfig() {}
}
