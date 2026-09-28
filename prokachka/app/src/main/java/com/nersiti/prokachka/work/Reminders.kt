package com.nersiti.prokachka.work

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.nersiti.prokachka.MainActivity
import com.nersiti.prokachka.R
import com.nersiti.prokachka.core.DayKind
import com.nersiti.prokachka.core.ProgramCalendar
import com.nersiti.prokachka.core.Schedule
import com.nersiti.prokachka.data.AppDatabase
import com.nersiti.prokachka.data.toDomain
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.util.concurrent.TimeUnit

/** Ежедневное напоминание: что сегодня по программе, если день ещё не выполнен. */
class ReminderWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val stored = AppDatabase.get(applicationContext).programDao().state()?.toDomain() ?: return Result.success()
        val state = ProgramCalendar.sync(stored, LocalDate.now())
        if (state.isDone) return Result.success()
        val text = when (state.kind) {
            DayKind.TEST -> "Тест 1-го дня: узнаем твою стартовую силу"
            DayKind.FINAL_TEST -> "Финальный тест! Посмотрим, сколько ты прокачался"
            DayKind.WORKOUT -> "Тренировка «${Schedule.template(state.mode, state.day).title}» ждёт"
            DayKind.STRETCH -> "День отдыха: 10 минут растяжки сохранят серию"
        }
        Reminders.notify(applicationContext, "День ${state.day}/${Schedule.DAYS}", text)
        return Result.success()
    }
}

object Reminders {
    private const val CHANNEL = "reminders"
    private const val WORK = "daily_reminder"

    fun createChannel(context: Context) {
        val channel = NotificationChannel(CHANNEL, "Напоминания о тренировках", NotificationManager.IMPORTANCE_DEFAULT)
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    fun schedule(context: Context, enabled: Boolean, minutesOfDay: Int) {
        val manager = WorkManager.getInstance(context)
        if (!enabled) {
            manager.cancelUniqueWork(WORK)
            return
        }
        val now = LocalDateTime.now()
        var next = LocalDate.now().atTime(LocalTime.of(minutesOfDay / 60, minutesOfDay % 60))
        if (!next.isAfter(now)) next = next.plusDays(1)
        val request = PeriodicWorkRequestBuilder<ReminderWorker>(1, TimeUnit.DAYS)
            .setInitialDelay(Duration.between(now, next).toMinutes(), TimeUnit.MINUTES)
            .build()
        manager.enqueueUniquePeriodicWork(WORK, ExistingPeriodicWorkPolicy.UPDATE, request)
    }

    fun notify(context: Context, title: String, text: String) {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        if (android.os.Build.VERSION.SDK_INT >= 33 && !granted) return
        val intent = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(intent)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(1, notification)
    }
}
