from pathlib import Path

from ai_core.core.hardware import detect_hardware_info, parse_total_ram_gb


def test_parse_total_ram_gb_from_meminfo() -> None:
    meminfo = "MemTotal:       16777216 kB\nMemFree:         1024 kB\n"

    ram_gb = parse_total_ram_gb(meminfo)

    assert ram_gb == 16.0


def test_detect_hardware_info_reads_ram_and_cpu(tmp_path: Path) -> None:
    meminfo_path = tmp_path / "meminfo"
    meminfo_path.write_text("MemTotal:        8388608 kB\n", encoding="utf-8")

    hardware = detect_hardware_info(meminfo_path=meminfo_path, cpu_count_provider=lambda: 6)

    assert hardware == {"ram_gb": 8.0, "cpu_cores": 6}
