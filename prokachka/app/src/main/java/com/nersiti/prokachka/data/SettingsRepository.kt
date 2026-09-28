package com.nersiti.prokachka.data

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.nersiti.prokachka.core.Inventory
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json

enum class ThemeMode(val title: String) { SYSTEM("Как в системе"), DARK("Тёмная"), LIGHT("Светлая") }

enum class ChecklistItem(val title: String) { SLEEP("Сон 7–9 часов"), PROTEIN("Белок"), WATER("Вода") }

data class Settings(
    val remindersEnabled: Boolean = true,
    /** Время напоминания в минутах от полуночи. */
    val reminderMinutes: Int = 18 * 60,
    val lockPhotos: Boolean = true,
    val theme: ThemeMode = ThemeMode.SYSTEM,
    val bodyWeightKg: Float? = null,
    val lastInventory: Inventory? = null,
    val checklistDay: Long = 0,
    val checklist: Set<ChecklistItem> = emptySet(),
) {
    fun checklistFor(day: LocalDate): Set<ChecklistItem> =
        if (checklistDay == day.toEpochDay()) checklist else emptySet()
}

private val Context.dataStore by preferencesDataStore(name = "settings")

@Singleton
class SettingsRepository @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val json = Json { ignoreUnknownKeys = true }

    val settings: Flow<Settings> = context.dataStore.data.map { it.toSettings() }

    suspend fun current(): Settings = settings.first()

    private fun Preferences.toSettings() = Settings(
        remindersEnabled = this[REMINDERS] ?: true,
        reminderMinutes = this[REMINDER_MINUTES] ?: (18 * 60),
        lockPhotos = this[LOCK] ?: true,
        theme = this[THEME]?.let { runCatching { ThemeMode.valueOf(it) }.getOrNull() } ?: ThemeMode.SYSTEM,
        bodyWeightKg = this[BODY_WEIGHT],
        lastInventory = this[INVENTORY]?.let { runCatching { json.decodeFromString(Inventory.serializer(), it) }.getOrNull() },
        checklistDay = this[CHECKLIST_DAY] ?: 0,
        checklist = this[CHECKLIST].orEmpty().mapNotNull { runCatching { ChecklistItem.valueOf(it) }.getOrNull() }.toSet(),
    )

    suspend fun setReminders(enabled: Boolean, minutes: Int) = context.dataStore.edit {
        it[REMINDERS] = enabled
        it[REMINDER_MINUTES] = minutes
    }

    suspend fun setLock(enabled: Boolean) = context.dataStore.edit { it[LOCK] = enabled }

    suspend fun setTheme(theme: ThemeMode) = context.dataStore.edit { it[THEME] = theme.name }

    suspend fun setBodyWeight(kg: Float?) = context.dataStore.edit {
        if (kg == null) it.remove(BODY_WEIGHT) else it[BODY_WEIGHT] = kg
    }

    suspend fun setInventory(inventory: Inventory) = context.dataStore.edit {
        it[INVENTORY] = json.encodeToString(Inventory.serializer(), inventory)
    }

    suspend fun toggleChecklist(item: ChecklistItem, today: LocalDate) = context.dataStore.edit {
        val day = today.toEpochDay()
        val current = if (it[CHECKLIST_DAY] == day) it[CHECKLIST].orEmpty() else emptySet()
        it[CHECKLIST_DAY] = day
        it[CHECKLIST] = if (item.name in current) current - item.name else current + item.name
    }

    private companion object {
        val REMINDERS = booleanPreferencesKey("reminders")
        val REMINDER_MINUTES = intPreferencesKey("reminder_minutes")
        val LOCK = booleanPreferencesKey("lock_photos")
        val THEME = stringPreferencesKey("theme")
        val BODY_WEIGHT = floatPreferencesKey("body_weight")
        val INVENTORY = stringPreferencesKey("last_inventory")
        val CHECKLIST_DAY = longPreferencesKey("checklist_day")
        val CHECKLIST = stringSetPreferencesKey("checklist")
    }
}
