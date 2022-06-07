import curses
import operator
from curses import wrapper
from curses.textpad import Textbox, rectangle
from dataclasses import dataclass
from enum import Enum
from math import floor
from os import get_terminal_size
from sys import exit
from time import sleep

import psutil
from psutil import Process


@dataclass(slots=True, frozen=True)
class ProcessData:
    name: str
    pid: int
    cpu_percent: float
    mem_percent: float


class ProcessHandler(object):
    def __init__(self) -> None:
        self.process_list: list[ProcessData] = []
        pass

    def generate_process_list(self, psutil_proc_list: list[Process]) -> None:
        for proc in psutil_proc_list:
            self.process_list.append(ProcessData(
                name=proc.name(),
                pid = proc.pid,
                cpu_percent=proc.cpu_percent(interval=1),
                mem_percent=proc.memory_percent()
            ))
        pass


class RecallWindow(Exception):
    def __init__(self, *args: object, recall_window: bool = True) -> None:
        self.recall_window = recall_window
        super().__init__(*args)


class SortingStrategy(Enum):
    BY_RAM_PERCENT = operator.methodcaller("memory_percent")
    BY_CPU_PERCENT = operator.methodcaller("cpu_percent", interval=0.5)
    BY_NAME = operator.methodcaller("name")
    BY_PID = operator.attrgetter("pid")


def get_processes(
    sorting_strategy: SortingStrategy | None = SortingStrategy.BY_CPU_PERCENT,
    sort_reversed: bool = False,
) -> list[Process]:
    pid_list = psutil.pids()
    if sorting_strategy is None:
        return [Process(pid) for pid in pid_list if psutil.pid_exists(pid)]
    sorted_list: list[Process] = [
        Process(pid) for pid in pid_list if psutil.pid_exists(pid)
    ]
    sorted_list.sort(key=sorting_strategy.value, reverse=sort_reversed)
    return sorted_list


def draw_load_bar(used: float, total: float, factor: int = 4) -> str:
    columns: int = get_terminal_size().columns // factor
    usage_percentage: float = (used / total) * 100
    bar_used: int = floor((usage_percentage * columns) // 100)
    return f"[ {'|'*bar_used}{' '*(columns-bar_used)} ] {usage_percentage:.2f}%"


def draw_rectangle(screen) -> None:
    screen.clear()

    # Rectangle for list processes
    rectangle(
        screen, 4, 1, get_terminal_size().lines - 4, get_terminal_size().columns // 2
    )

    rectangle(screen, 1, 1, 3, get_terminal_size().columns // 2 - 0)

    # Rectangle for overall system usage
    rectangle(
        screen,
        1,
        get_terminal_size().columns // 2 + 1,
        get_terminal_size().lines - 4,
        get_terminal_size().columns - 2,
    )

    # Rectangle for other system data
    rectangle(
        screen,
        get_terminal_size().lines - 3,
        1,
        get_terminal_size().lines - 1,
        get_terminal_size().columns - 2,
    )
    screen.refresh()

def start_monitor(stdscr) -> int:
    sorting_strategy = None
    lines = 0
    cols = 0
    VERTICAL_SCROLL = 0
    stdscr.nodelay(True)
    sort_reverse: bool = False
    max_name_len = 0

    while True:

        battery = psutil.sensors_battery()

        if battery:
            battery_percent = f"{battery.percent:.2f}"
            battery_status = "Charging" if battery.power_plugged else "Discharging"
        else:
            battery_percent = "Not found"
            battery_status = "Unknown"

        pid_list = get_processes(sorting_strategy, sort_reverse)
        pid_len = len(pid_list)

        if VERTICAL_SCROLL >= pid_len:
            VERTICAL_SCROLL = pid_len - 1

        if lines != get_terminal_size().lines or cols != get_terminal_size().columns:
            lines = get_terminal_size().lines
            cols = get_terminal_size().columns
            draw_rectangle(stdscr)

        max_name_len = cols // 2 - 52
        max_name_len = max_name_len if max_name_len >= 10 else 10

        status_bar = curses.newwin(1, cols - 6, lines - 2, 3)
        status_bar.addstr(
            f"SORT_{sorting_strategy.name if sorting_strategy is not None else 'Nothing':{15}}"
            + f"reverse sort: {sort_reverse}{'':{5}}"
            + f"Battery: {battery_percent:{10}}|{battery_status:{15}}"
            + f"Scroll: {VERTICAL_SCROLL}|{pid_len}"
        )
        status_bar.refresh()

        proc_pad = curses.newpad(pid_len, cols)

        title_win = curses.newwin(1, cols // 2 - 4, 2, 2)
        title_win.addstr(
            f"{'PID':{9}}|{'Name':{max_name_len+2}}|MEM_PERCENT  |CPU_PERCENT"
        )
        title_win.refresh()

        data_pad = curses.newwin(lines // 2, cols // 2 - 4, 2, cols // 2 + 2)
        data_pad.addstr(
            f"Total CPU: {draw_load_bar(psutil.cpu_percent(), 100, factor=4)}\n"
        )

        for idx, percpu_usage in enumerate(psutil.cpu_percent(percpu=True)):
            data_pad.addstr(
                f"{'CPU_'+str(idx)+':':{10}} {draw_load_bar(percpu_usage, 100, factor=4)}\n"
            )

        data_pad.addstr("-" * (cols // 2 - 4))
        data_pad.addstr(f"MEM_USAGE: {draw_load_bar(psutil.virtual_memory().percent, 100, factor=4)}\n")
        data_pad.refresh()

        for idx, process in enumerate(pid_list):
            if psutil.pid_exists(process.pid):
                name = process.name()

                name = (
                    name
                    if len(name) < max_name_len
                    else name[: max_name_len - 2] + ".."
                )

                proc_pad.addstr(
                    idx,
                    0,
                    f"[{process.pid:{6}}] "
                    + f"[{name:{max_name_len}}] "
                    + f" {process.memory_percent():.5f}{'%':{5}}"
                    + f"{process.cpu_percent():.2f}{'%':{4}}",
                )

        proc_pad.refresh(
            0 + VERTICAL_SCROLL,
            0,
            5,
            2,
            get_terminal_size().lines - 6,
            (cols // 2) - 2,
        )

        try:
            key = stdscr.getkey()

        except:
            sleep(0.5)
            pass

        else:

            if key == "q":
                break

            elif key == "KEY_DOWN":
                if VERTICAL_SCROLL < pid_len - 1:
                    VERTICAL_SCROLL += 1

            elif key == "KEY_UP":
                if VERTICAL_SCROLL > 0:
                    VERTICAL_SCROLL -= 1

            elif key == "s":
                try:
                    curses.halfdelay(2)
                    next_key = stdscr.getkey()

                except:
                    sorting_strategy = None

                else:
                    if next_key == "c":
                        sorting_strategy = SortingStrategy.BY_CPU_PERCENT
                    elif next_key == "r":
                        sorting_strategy = SortingStrategy.BY_RAM_PERCENT
                    elif next_key == "p":
                        sorting_strategy = SortingStrategy.BY_PID
                    elif next_key == "n":
                        sorting_strategy = SortingStrategy.BY_NAME
                    elif next_key == "6":
                        sort_reverse = not sort_reverse
                    else:
                        sorting_strategy = None

                finally:
                    curses.nocbreak()
                    curses.cbreak()
                    stdscr.nodelay(True)

            stdscr.refresh()
            proc_pad.refresh(
                0 + VERTICAL_SCROLL,
                0,
                5,
                2,
                get_terminal_size().lines - 6,
                (cols // 2) - 2,
            )
            continue
    return 0


def main() -> int:
    try:
        return wrapper(start_monitor)
    except KeyboardInterrupt:
        return 130
    except curses.error as err:
        for x in err.args:
            if "addwstr()" in x:
                print("Please use a larger terminal window...")
            elif "wmove()" in x:
                print(x)
                return main()
            else:
                print(x)
        return 1


if __name__ == "__main__":
    exit(main())
