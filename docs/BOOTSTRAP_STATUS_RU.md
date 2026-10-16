# Фактическое состояние bootstrap, 2026-10-16

Проверено через локальный SSH-клиент на root@62.171.140.149.

- Ubuntu 24.04.5 LTS, KVM, 8 vCPU AMD EPYC, около 23 GiB RAM, swap нет.
- Ядро работает 6.8.0-139; reboot-required от linux-image-6.8.0-147-generic
  и linux-base. Перезагрузка не выполнялась, Ubuntu release не менялся.
- Созданы kyrylo (sudo) и ihor (без sudo), отдельные home 750 и .ssh 700.
  Установлены разные персональные публичные ключи из id_ed25519_kyrylo.pub
  и id_rsa_ihor.pub. Отдельный вход kyrylo по ключу проверен. Его личный пароль
  установлен через локальные защищённые окна; sudo через новый SSH-вход
  проверен командой id -u (результат 0). Пароль ihor остаётся заблокированным;
  реальный вход ihor со своего компьютера ещё не проверен.
- Root SSH и его настройки оставлены рабочими. Группа docker пуста.
- Docker Engine 29.9.1, Compose v5.6.0, containerd, buildx установлены из
  официального репозитория Docker для Noble. hello-world выполнен успешно.
  Docker/containerd active и enabled; проверка после reboot ещё не выполнена.
- Docker logging=local, 10m x 3 по умолчанию, live-restore=true. Journald:
  SystemMaxUse=512M, RuntimeMaxUse=128M, MaxRetentionSec=14day.
- Автоматический reboot через unattended-upgrades явно выключен.
- UFW подготовлен, но пока inactive: IPv4/IPv6 SSH TCP/22 и PZ UDP/16261–16262.
  TCP 80/443 не открыт. Включение firewall ожидает подтверждения и нового
  SSH-теста с автоматическим откатом.
  Подготовлен, но не запущен /usr/local/sbin/enable-ufw-with-rollback:
  systemd timer отключит UFW через три минуты, если оператор после НОВОГО
  SSH-входа не отменит rollback. Ожидается отдельное подтверждение включения.
- docker-ingress-guard.service ограничивает внешний forwarding с eth0:
  established/related и UDP 16261/16262 разрешены; прочие новые входящие в
  Docker bridges запрещены. На текущем VPS IPv4 и IPv6 через DOCKER-USER;
  предусмотрен fallback FORWARD на docker0/br+. Это не заменяет внешнее
  сканирование и UFW INPUT.
- vps-monitor.timer каждые пять минут пишет CPU/steal, RAM, диск, контейнеры,
  failed units и последний local backup в /var/log/vps-monitor/latest.txt.
  Внешние оповещения ещё не настроены.
- Системный Nginx установлен, active/enabled, nginx -t успешен. Default site
  отключён до запуска службы, 80/443 не слушают. SaaS-каркас пока только в PR.
- networkd/resolved работают, IPv4/IPv6 маршруты есть. eth0 остаётся
  routable/configuring; wait-online завершился timeout. Cloud-init init
  сообщает ошибку bootcmd (exit 1). Последняя provider-команда — pkill -HUP
  sshd; она выполнялась до генерации host keys, поэтому вероятная причина —
  отсутствие процесса sshd на тот момент. Это вывод по последовательности
  событий, не доказательство трассировкой shell. Drop-in wait-online содержит
  две последовательные ExecStart; networkd видит IPv4/IPv6 как routable/online,
  но завершение настройки eth0/routes остаётся pending. Не перезапускать
  cloud-init и не менять сеть вслепую.
- Registry metadata закреплённого PZ digest: версия 42.21.0, Steam public,
  buildId 25485538, upstream revision bec4ac61968b5212fe8047185092e19bf194f374.
  Исходники entrypoint/init проверены на этой revision. Образ загружен на VPS;
  изолированный тест без сети подтвердил baked buildId 25485538, файлы игры/JRE
  и удаление строки, печатающей пароль (exit 0). Игровой мир не запускался,
  версия при игровом старте и клиентские UDP-тесты ещё не подтверждены.
- После загрузки образа: около 22 GiB RAM available и 278 GiB диска свободно.
- Подтверждённая владельцем конфигурация commit
  6e2436fc9c35692b8265276618c205dad0b1bc71 скопирована в
  /opt/zomboid-server; shell syntax и оба Compose-шаблона проверены на VPS.
  Игровые секреты ещё не записаны: защищённый ввод отменён пользователем.
  Runtime .env отсутствует, мир и игровые backup ещё не создавались.

Секреты, runtime .env, приватные ключи, игровые данные и архивы в Git не добавлялись.
Rescue/VNC, подтверждение firewall/reboot, повторный защищённый ввод игровых
секретов, offsite backup и канал оповещений требуют участия владельца.
Приложения не считать развёрнутыми по наличию Compose-шаблонов.
