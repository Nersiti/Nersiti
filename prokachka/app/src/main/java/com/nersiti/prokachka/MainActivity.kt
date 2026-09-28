package com.nersiti.prokachka

import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.getValue
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nersiti.prokachka.data.Settings
import com.nersiti.prokachka.data.SettingsRepository
import com.nersiti.prokachka.data.ThemeMode
import com.nersiti.prokachka.ui.AppNavHost
import com.nersiti.prokachka.ui.photo.HardwareKeys
import com.nersiti.prokachka.ui.theme.ProkachkaTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/** FragmentActivity нужна для BiometricPrompt. */
@AndroidEntryPoint
class MainActivity : FragmentActivity() {

    @Inject
    lateinit var settingsRepository: SettingsRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val settings by settingsRepository.settings.collectAsStateWithLifecycle(initialValue = Settings())
            val dark = when (settings.theme) {
                ThemeMode.SYSTEM -> isSystemInDarkTheme()
                ThemeMode.DARK -> true
                ThemeMode.LIGHT -> false
            }
            ProkachkaTheme(darkTheme = dark) {
                AppNavHost()
            }
        }
    }

    /** Кнопка громкости делает снимок, когда открыт экран фото. */
    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        val volume = keyCode == KeyEvent.KEYCODE_VOLUME_DOWN || keyCode == KeyEvent.KEYCODE_VOLUME_UP
        if (volume && HardwareKeys.captureEnabled) {
            HardwareKeys.events.tryEmit(Unit)
            return true
        }
        return super.onKeyDown(keyCode, event)
    }
}
