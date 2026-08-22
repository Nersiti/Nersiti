package org.telegram.nersiti;

import java.io.DataOutputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * HTTP-клиент к бэкенду-мозгу на ПК. Все вызовы делать в фоновом потоке.
 * Эндпоинты: /sync/messages, /sync/media, /ai/reply, /health (см. PLAN.md §6b).
 */
public class NersitiSync {

    /** POST /sync/messages — JSON-пачка сообщений. Возвращает код ответа. */
    public static int syncMessages(String jsonBody) throws Exception {
        HttpURLConnection c = open("/sync/messages", "POST");
        c.setRequestProperty("Content-Type", "application/json");
        writeBody(c, jsonBody.getBytes(StandardCharsets.UTF_8));
        int code = c.getResponseCode();
        c.disconnect();
        return code;
    }

    /**
     * POST /ai/reply — {chat_id, incoming_text}. Возвращает тело ответа
     * ({"action":"send|draft|none","text":"..."}). Парсинг — на стороне UI.
     */
    public static String requestReply(long chatId, String incomingText) throws Exception {
        String body = "{\"chat_id\":" + chatId + ",\"incoming_text\":" +
                jsonString(incomingText) + "}";
        HttpURLConnection c = open("/ai/reply", "POST");
        c.setRequestProperty("Content-Type", "application/json");
        writeBody(c, body.getBytes(StandardCharsets.UTF_8));
        String resp = readAll(c);
        c.disconnect();
        return resp;
    }

    /** GET /health — доступность мозга. */
    public static boolean health() {
        try {
            HttpURLConnection c = open("/health", "GET");
            int code = c.getResponseCode();
            c.disconnect();
            return code == 200;
        } catch (Exception e) {
            return false;
        }
    }

    // ---- служебное ----
    private static HttpURLConnection open(String path, String method) throws Exception {
        URL url = new URL(NersitiConfig.BACKEND_URL + path);
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setRequestMethod(method);
        c.setConnectTimeout(8000);
        c.setReadTimeout(120000);
        c.setRequestProperty("X-Sync-Token", NersitiConfig.SYNC_TOKEN);
        if (!"GET".equals(method)) {
            c.setDoOutput(true);
        }
        return c;
    }

    private static void writeBody(HttpURLConnection c, byte[] data) throws Exception {
        try (OutputStream os = new DataOutputStream(c.getOutputStream())) {
            os.write(data);
        }
    }

    private static String readAll(HttpURLConnection c) throws Exception {
        java.io.InputStream is = (c.getResponseCode() < 400)
                ? c.getInputStream() : c.getErrorStream();
        java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = is.read(buf)) != -1) bos.write(buf, 0, n);
        return new String(bos.toByteArray(), StandardCharsets.UTF_8);
    }

    private static String jsonString(String s) {
        if (s == null) return "\"\"";
        StringBuilder b = new StringBuilder("\"");
        for (char ch : s.toCharArray()) {
            switch (ch) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default: b.append(ch);
            }
        }
        return b.append("\"").toString();
    }
}
