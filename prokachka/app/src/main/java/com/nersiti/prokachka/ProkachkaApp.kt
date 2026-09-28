package com.nersiti.prokachka

import android.app.Application
import com.nersiti.prokachka.data.SettingsRepository
import com.nersiti.prokachka.work.Reminders
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

@HiltAndroidApp
class ProkachkaApp : Application() {

    @Inject
    lateinit var settings: SettingsRepository

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override fun onCreate() {
        super.onCreate()
        Reminders.createChannel(this)
        scope.launch {
            val current = settings.current()
            Reminders.schedule(this@ProkachkaApp, current.remindersEnabled, current.reminderMinutes)
        }
    }
}
