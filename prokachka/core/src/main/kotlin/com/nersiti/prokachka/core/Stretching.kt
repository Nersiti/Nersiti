package com.nersiti.prokachka.core

data class Stretch(val name: String, val seconds: Int, val perSide: Boolean = false, val tip: String)

/** Растяжка в дни отдыха: 10 минут, засчитывается в серию. */
object Stretching {
    const val MINUTES = 10

    val routine = listOf(
        Stretch("Вращения плечами и руками", 60, tip = "Медленные круги вперёд и назад, разогрей суставы."),
        Stretch("Растяжка груди у стены", 45, perSide = true, tip = "Предплечье на стене, мягко разворачивай корпус от неё."),
        Stretch("Растяжка плеча поперёк груди", 30, perSide = true, tip = "Прижми прямую руку к груди другой рукой."),
        Stretch("Растяжка трицепса за головой", 30, perSide = true, tip = "Локоть вверх, ладонь тянется к лопатке."),
        Stretch("Поза ребёнка", 60, tip = "Сядь на пятки, руки вытяни вперёд, расслабь спину."),
        Stretch("Кошка-корова", 60, tip = "На четвереньках попеременно выгибай и округляй спину."),
        Stretch("Выпад с растяжкой бедра", 45, perSide = true, tip = "Колено задней ноги на полу, таз подай вперёд."),
        Stretch("Растяжка задней поверхности бедра", 45, perSide = true, tip = "Сидя, тянись к стопе прямой ноги, спина ровная."),
        Stretch("«Голубь» для ягодиц", 45, perSide = true, tip = "Согнутая нога перед собой, вторая вытянута назад."),
        Stretch("Растяжка икр у стены", 30, perSide = true, tip = "Пятка задней ноги прижата к полу, колено прямое."),
    )

    val totalSeconds: Int get() = routine.sumOf { it.seconds * if (it.perSide) 2 else 1 }
}
