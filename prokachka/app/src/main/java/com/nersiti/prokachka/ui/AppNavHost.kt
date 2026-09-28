package com.nersiti.prokachka.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarToday
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.ui.inventory.InventoryScreen
import com.nersiti.prokachka.ui.onboarding.OnboardingScreen
import com.nersiti.prokachka.ui.onboarding.TestScreen
import com.nersiti.prokachka.ui.photo.PhotoScreen
import com.nersiti.prokachka.ui.progress.ProgressScreen
import com.nersiti.prokachka.ui.settings.SettingsScreen
import com.nersiti.prokachka.ui.today.StretchScreen
import com.nersiti.prokachka.ui.today.TodayScreen
import com.nersiti.prokachka.ui.workout.SummaryScreen
import com.nersiti.prokachka.ui.workout.WorkoutScreen
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

object Routes {
    const val ONBOARDING = "onboarding"
    const val TODAY = "today"
    const val INVENTORY = "inventory"
    const val PHOTO = "photo/{next}"
    const val TEST = "test"
    const val WORKOUT = "workout"
    const val SUMMARY = "summary"
    const val STRETCH = "stretch"
    const val PROGRESS = "progress"
    const val SETTINGS = "settings"

    /** После фото: тест или тренировка. */
    fun photo(next: String) = "photo/$next"
}

@HiltViewModel
class RootViewModel @Inject constructor(repository: ProgramRepository) : ViewModel() {
    /** null — ещё загружается, false — нужен онбординг. */
    val hasProgram = repository.state.map { it != null }
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)
}

private data class Tab(val route: String, val title: String, val icon: ImageVector)

private val tabs = listOf(
    Tab(Routes.TODAY, "Сегодня", Icons.Default.CalendarToday),
    Tab(Routes.PROGRESS, "Прогресс", Icons.Default.Insights),
    Tab(Routes.SETTINGS, "Настройки", Icons.Default.Settings),
)

@Composable
fun AppNavHost(root: RootViewModel = hiltViewModel()) {
    val hasProgram by root.hasProgram.collectAsStateWithLifecycle()
    // Стартовый экран выбирается один раз: иначе после онбординга граф навигации пересоздался бы.
    var start by rememberSaveable { mutableStateOf<String?>(null) }
    if (start == null) {
        start = when (hasProgram) {
            null -> null
            true -> Routes.TODAY
            false -> Routes.ONBOARDING
        }
    }
    val startRoute = start ?: run {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        return
    }

    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val current = entry?.destination?.route
    Scaffold(
        bottomBar = {
            if (tabs.any { it.route == current }) {
                NavigationBar {
                    tabs.forEach { tab ->
                        NavigationBarItem(
                            selected = current == tab.route,
                            onClick = { nav.switchTab(tab.route) },
                            icon = { Icon(tab.icon, contentDescription = null) },
                            label = { Text(tab.title) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(nav, startDestination = startRoute, modifier = Modifier.padding(bottom = padding.calculateBottomPadding())) {
            composable(Routes.ONBOARDING) {
                OnboardingScreen(onStarted = { nav.navigate(Routes.photo("test")) { popUpTo(0) } })
            }
            composable(Routes.TODAY) {
                TodayScreen(
                    onStartTest = { nav.navigate(Routes.photo("test")) },
                    onStartWorkout = { nav.navigate(Routes.INVENTORY) },
                    onStartStretch = { nav.navigate(Routes.STRETCH) },
                )
            }
            composable(Routes.INVENTORY) {
                InventoryScreen(
                    onBack = { nav.popBackStack() },
                    onReady = { nav.navigate(Routes.photo("workout")) },
                )
            }
            composable(Routes.PHOTO, arguments = listOf(navArgument("next") { type = NavType.StringType })) { back ->
                val next = back.arguments?.getString("next") ?: "workout"
                PhotoScreen(
                    onBack = { nav.popBackStack() },
                    onDone = {
                        nav.navigate(if (next == "test") Routes.TEST else Routes.WORKOUT) {
                            popUpTo(Routes.PHOTO) { inclusive = true }
                        }
                    },
                )
            }
            composable(Routes.TEST) {
                TestScreen(onDone = { nav.goToday() })
            }
            composable(Routes.WORKOUT) {
                WorkoutScreen(
                    onExit = { nav.goToday() },
                    onFinished = { nav.navigate(Routes.SUMMARY) { popUpTo(Routes.WORKOUT) { inclusive = true } } },
                )
            }
            composable(Routes.SUMMARY) {
                SummaryScreen(onDone = { nav.goToday() })
            }
            composable(Routes.STRETCH) {
                StretchScreen(onBack = { nav.popBackStack() }, onDone = { nav.goToday() })
            }
            composable(Routes.PROGRESS) { ProgressScreen() }
            composable(Routes.SETTINGS) {
                SettingsScreen(onRestarted = { nav.navigate(Routes.ONBOARDING) { popUpTo(0) } })
            }
        }
    }
}

private fun NavHostController.goToday() = navigate(Routes.TODAY) {
    popUpTo(0)
    launchSingleTop = true
}

private fun NavHostController.switchTab(route: String) = navigate(route) {
    popUpTo(Routes.TODAY) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
