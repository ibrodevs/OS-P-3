# OS-P-3 — процессы Linux, `/proc`, `fork`, `exec` и Copy-on-Write

Решение **варианта B**. Все скрипты рассчитаны на Linux и Python 3. Для `ptree.py` команда `ps` не используется: информация о процессах читается напрямую из `/proc`.

## 1. `ptree.py` — дерево процессов текущего пользователя

Скрипт проходит по каталогам `/proc/<PID>`, читает `/proc/<PID>/status`, оставляет процессы текущего UID и строит дерево по `PPid`.

Для каждого процесса выводятся:

- PID;
- состояние (`R`, `S`, `Z` и т. д.);
- RSS в KiB;
- имя процесса.

Запуск:

```bash
python3 ptree.py
```

Пример:

```text
bash (PID=1821, state=S, RSS=5324 kB)
  python3 (PID=1904, state=R, RSS=10188 kB)
systemd (PID=1200, state=S, RSS=11920 kB)
  dbus-daemon (PID=1215, state=S, RSS=4140 kB)
```

> Процессы могут появляться и исчезать прямо во время чтения `/proc`, поэтому такие гонки обрабатываются и не считаются ошибкой.

## 2. `runner.py` — запуск N дочерних процессов через `fork` + `exec`

Родитель создаёт `N` детей с помощью `os.fork()`. Каждый ребёнок заменяет себя переданной программой через `os.execvp()`. Родитель ждёт всех через `waitpid()` и печатает код возврата и время работы каждого процесса.

Запуск:

```bash
python3 runner.py 3 -- /bin/sleep 1
```

Пример с ненулевым кодом возврата:

```bash
python3 runner.py 2 -- /bin/sh -c 'sleep 0.1; exit 3'
```

Пример вывода:

```text
PID 416: return=3 (exit code 3), runtime=0.105 s
PID 417: return=3 (exit code 3), runtime=0.103 s
```

Если процесс завершится сигналом, `runner.py` также покажет номер/имя сигнала и shell-compatible код `128 + signal`.

## 3. Зомби — `zombie_demo.py`

Ребёнок завершается сразу, а родитель специально некоторое время **не вызывает `waitpid()`**. Пока родитель не забрал статус завершения, запись ребёнка остаётся в таблице процессов в состоянии `Z` — это zombie.

Запуск:

```bash
python3 zombie_demo.py
```

Фрагмент `ps`, полученный во время демонстрации:

```text
    PID    PPID S STAT CMD
    435     434 S Sl   python3 zombie_demo.py
    447     435 Z Z    [python3] <defunct>
```

Здесь PID `447` уже завершил выполнение, но его родитель PID `435` ещё не вызвал `waitpid()`. После `waitpid()` zombie исчезает.

Для ручной проверки, пока скрипт держит zombie около 10 секунд, можно выполнить:

```bash
ps -o pid,ppid,state,stat,cmd -p <PARENT_PID>,<CHILD_PID>
```

## 4. Сирота — `orphan_demo.py`

Родитель создаёт ребёнка и сразу завершается. Ребёнок продолжает работу и через `getppid()` определяет нового родителя. Затем скрипт показывает его через `ps`.

Запуск:

```bash
python3 orphan_demo.py
```

Пример вывода из тестовой Linux-среды:

```text
[parent] PID=457 created child PID=467 and exits now
[child] PID=467; PPID just after fork=1 (supervisord)
[child] original parent is gone; new PPID=1 (supervisord)

ps after re-parenting:
    PID    PPID S STAT CMD
      1       0 S S+   /usr/bin/python3 /usr/bin/supervisord -n -c /etc/supervisord.conf
    467       1 S S    python3 orphan_demo.py

Adopter on this run: PID 1 (supervisord).
```

В этой среде сироту усыновил **PID 1**. На обычной Linux-системе это часто `systemd`/`init`. Если процесс запускается внутри окружения, где настроен **subreaper** (например, менеджер процессов или некоторые user-session сервисы), сироту может принять не PID 1. Поэтому `orphan_demo.py` специально выводит реальный PID и имя усыновившего процесса на той системе, где его запустили.

## 5. Copy-on-Write — `cow_demo.py`

`fork()` не копирует всю память процесса немедленно. Родитель и ребёнок сначала используют одни и те же физические страницы памяти только для чтения. Когда ребёнок пытается изменить страницу, ядро создаёт для него отдельную копию этой страницы. Это и есть **Copy-on-Write (CoW)**.

Скрипт создаёт большой Python-список из блоков `bytearray`, заранее трогает страницы в родителе, делает `fork()`, затем измеряет память ребёнка **до** и **после** изменения унаследованного списка.

Запуск:

```bash
python3 cow_demo.py
```

Или с другим размером:

```bash
python3 cow_demo.py --size-mb 128
```

Пример для 16 MiB payload:

```text
Parent PID=376 prepared 4096 blocks (~16 MiB payload)
Child PID=429 inherited the list from parent
child before writes: RSS=95636 kB, PSS=48468 kB, Shared_Dirty=92900 kB, Private_Dirty=1488 kB, minor_faults=599
child after writes : RSS=95840 kB, PSS=56869 kB, Shared_Dirty=76252 kB, Private_Dirty=18140 kB, minor_faults=4797
Parent: child finished; original list is unchanged in the parent.
```

Что видно:

- сразу после `fork()` ребёнок уже видит большой список, но страницы в основном разделяются с родителем;
- после записей `Private_Dirty` заметно растёт, а `Shared_Dirty` уменьшается — изменённые страницы стали приватными копиями ребёнка;
- число minor page faults увеличивается, потому что записи запускают механизм CoW;
- RSS может увеличиться совсем немного. Это нормально: RSS учитывает как shared, так и private resident pages, поэтому замена shared-страницы её private-копией не обязана удваивать RSS.

Таким образом, память после `fork()` копируется **лениво, по мере записи в отдельные страницы**, а не целиком в момент `fork()`.

## Быстрая проверка всех файлов

```bash
python3 -m py_compile ptree.py runner.py zombie_demo.py orphan_demo.py cow_demo.py
python3 ptree.py
python3 runner.py 3 -- /bin/echo hello
python3 zombie_demo.py
python3 orphan_demo.py
python3 cow_demo.py --size-mb 64
```

## Файлы

```text
README.md
ptree.py
runner.py
zombie_demo.py
orphan_demo.py
cow_demo.py
```
