package com.nersiti.prokachka.data

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow

enum class PhotoAngle(val title: String) { FRONT("Фронт"), SIDE("Бок"), BACK("Спина") }

/** Фото лежат во внутренней папке приложения: в галерею они не попадают. */
@Singleton
class PhotoStorage @Inject constructor(
    @ApplicationContext context: Context,
    db: AppDatabase,
) {
    private val dir = File(context.filesDir, "photos").apply { mkdirs() }
    private val dao = db.photoDao()

    val photos: Flow<List<PhotoEntity>> = dao.observePhotos()

    fun newFile(cycle: Int, day: Int, angle: PhotoAngle): File =
        File(dir, "c${cycle}_d${day}_${angle.name.lowercase()}_${System.currentTimeMillis()}.jpg")

    suspend fun save(cycle: Int, day: Int, angle: PhotoAngle, file: File, today: LocalDate) {
        dao.insert(PhotoEntity(cycle = cycle, day = day, angle = angle.name, path = file.absolutePath, takenOn = today.toEpochDay()))
    }

    suspend fun last(angle: PhotoAngle): PhotoEntity? = dao.lastPhoto(angle.name)

    suspend fun taken(cycle: Int, day: Int): Set<PhotoAngle> =
        dao.photos().filter { it.cycle == cycle && it.day == day }.map { PhotoAngle.valueOf(it.angle) }.toSet()
}
