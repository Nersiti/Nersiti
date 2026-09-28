pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "Prokachka"

include(":app")

// Ядро на чистом Kotlin: собирается и тестируется без Android SDK (`./gradlew -p core test`).
includeBuild("core")
