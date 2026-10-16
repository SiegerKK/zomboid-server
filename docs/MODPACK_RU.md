# Модпак со скриншота — Project Zomboid Build 42.21.0

Список из 12 пунктов. **Статус: staged, не установлен и не проверен в игре.** Перед запуском сделайте холодный backup нового мира, disposable тестовый запуск и проверьте версии/зависимости. Моды для 42.20 могут быть несовместимы с 42.21.0.

| Мод | Внутренний Mod ID | Workshop ID | План |
| --- | --- | --- | --- |
| ZombieBuddy | ZombieBuddy | 3619862853 | Сервер; проверить Java agent на Linux и security |
| Bandits | Bandits2 | 3469292499 | Сервер; NPC AI, проверить мультиплеер |
| Bandits Creator | BanditsCreator | 3378285185 | Сервер; зависимости Bandits |
| Viewpoint | Viewpoint | 3809306528 | Сервер; проверить dedicated MP |
| Immersive Driving | ImmersiveDriving | 3817413313 | Сервер + клиент; совместная езда |
| [B42.20] TLOU Infected | TLOU_Infected_42_20 | 3776164832 | Сервер; проверить B42.21 |
| [B42.20] Zomboid Forge | ZomboidForge | 3776274080 | Сервер; проверить B42.21 |
| Starlit Library | StarlitLibrary | 3268487204 | Библиотека зависимостей |
| Viewpoint - Barricade Fix | ViewpointBarricade | 3815033191 | Кандидат client-only, проверить |
| Viewpoint Immersive Camera Motion | ViewpointBodycam | 3818432217 | Кандидат client-only, проверить |
| Viewpoint: Living Props | ViewpointLivingProps | 3816442251 | Client-only по автору |
| Death Cam for Viewpoint | ViewpointDeathCam | **не подтверждён** | Идентификатор получить из Steam/локального mod.info |

В `config/mods.env` внесены 8 модов основного серверного набора. Четыре Camera/Viewpoint addons находятся в документации, не активируются сервером без проверки. Не принимайте порядок таблицы за гарантированный порядок зависимостей: проверьте документацию Workshop и mod.info.

## Последовательность тестов

1. Если ванильный сервер работает, остановить штатно (только при отсутствии игроков) и выполнить cold backup. Не удалять мир/volume.
2. Сверить каждый URL Steam Workshop, текущую поддержку Build 42.21 и зависимости. ZombieBuddy требует отдельного внимания к Java-agent и Linux.
3. Поднять тестовый мир с отдельным data volume, не используя production save. Установить набор core mods, проверить server log и предметы/NPC, тест соединения двух клиентов.
4. Добавлять клиентские дополнения на компьютеры игроков, а не автоматически в server JVM. Для неизвестного Death Cam установить ID из реального Steam Workshop и `mod.info`, не угадывать.
5. Проверить совместную поездку, Bandits NPC и TLOU infected, расход памяти; только после успешного теста применять изменения к production. Модификации с 42.20 не активировать, если обнаружены ошибки совместимости.

Никакие пароли/данные пользователей не хранить в GitHub.
