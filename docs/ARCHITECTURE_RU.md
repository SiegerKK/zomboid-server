# Архитектура VPS (24 GB)

Изолированные стеки: `pz` для Project Zomboid Build 42 (UDP 16261/16262; отдельные save и Workshop volumes; Java heap 8192m, Docker mem 12g) и `saas` (frontend Nginx, backend, внутренняя PostgreSQL при необходимости). Host Nginx принимает HTTPS и проксирует только на `127.0.0.1:18080`, который опубликован SaaS-Nginx. БД, RCON и Docker API не публикуются.

Ubuntu 24.04.5 LTS, Contabo IPv4 62.171.140.149, два SSH пользователя kyrylo и ihor с независимыми ключами. Персональные роли; не добавлять обоих в docker group (root-equivalent). IPv6 firewall проверять отдельно. Docker published ports могут обходить стандартные UFW-цепочки. SaaS и Zomboid изолированы в Docker networks, но делят VPS CPU, память, диски и ядро ОС.

Постоянные данные Zomboid `/srv/zomboid/data`, Workshop `/srv/zomboid/workshop`, local backup `/srv/zomboid/backups`; отдельный SaaS volume `/srv/saas`. Зашифрованные offsite backups и тест восстановления обязательны перед production-использованием. Запрещены автоматические обновления модов посреди игры. Для SaaS нет пока ни домена, ни кода; не публиковать фиктивный production endpoint.
