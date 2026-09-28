package com.nersiti.prokachka.di

import android.content.Context
import com.nersiti.prokachka.core.ExerciseCatalog
import com.nersiti.prokachka.data.AppDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun database(@ApplicationContext context: Context): AppDatabase = AppDatabase.get(context)

    @Provides
    @Singleton
    fun catalog(): ExerciseCatalog = ExerciseCatalog.default
}
