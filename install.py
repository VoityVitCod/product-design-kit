#!/usr/bin/env python3
"""Подключить инструменты продуктового дизайна к рабочей папке. Python 3.8+."""

# VoityVIT

import argparse
import codecs
import sys
from pathlib import Path


KIT = Path(__file__).resolve().parent
STANDARDS = Path("design/PROJECT-STANDARDS.md")
ROOT_RULES = Path("AGENTS.md")
BEGIN = "<!-- product-design-kit -->"
END = "<!-- /product-design-kit -->"


def contents():
    files = [ROOT_RULES, Path("SUBAGENTS.md"), STANDARDS,
             Path("design/WORKING-AGREEMENT.md"), Path("design/RECIPES.md")]
    for folder, pattern in [
        (".codex/agents", "*.toml"),
        (".agents/skills/product-design-workflow", "**/*"),
    ]:
        found = sorted(p.relative_to(KIT) for p in (KIT / folder).glob(pattern)
                       if p.is_file() and not p.name.startswith("."))
        if not found:
            raise ValueError("В комплекте отсутствуют файлы " + folder)
        files.extend(found)
    return {name: (KIT / name).read_bytes() for name in files}


def rules_suffix(old, template, block):
    # Сохраняем кодировку и переносы существующего документа, дописываем только суффикс.
    encoding = "utf-8"
    prefix = b""
    for bom, codec in [(codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
                       (codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"),
                       (codecs.BOM_UTF8, "utf-8")]:
        if old.startswith(bom):
            prefix, encoding = bom, codec
            break
    try:
        text = old[len(prefix):].decode(encoding)
    except UnicodeDecodeError:
        raise ValueError("кодировка AGENTS.md не определена, укажите UTF-8 или Unicode с BOM")
    norm = text.replace("\r\n", "\n")
    if template.decode("utf-8").replace("\r\n", "\n").strip() in norm:
        return b""
    lines = norm.splitlines()
    if BEGIN in lines or END in lines:
        if lines.count(BEGIN) == lines.count(END) == 1 and lines.index(BEGIN) < lines.index(END):
            return b""
        raise ValueError("в AGENTS.md найден неполный или повторяющийся блок product-design-kit")
    newline = "\r\n" if "\r\n" in text else "\n"
    gap = ""
    if text and not text.endswith(newline * 2):
        gap = newline if text.endswith(newline) else newline * 2
    block_text = block.decode("utf-8").strip().replace("\r\n", "\n").replace("\n", newline)
    return (gap + block_text + newline).encode(encoding)


def check_path(root, name):
    current = root
    for part in name.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("символическая ссылка в пути " + str(current.relative_to(root)))
        if current.exists() and current != root / name and not current.is_dir():
            raise ValueError("вместо папки найден файл " + str(current.relative_to(root)))
    if current.exists() and not current.is_file():
        raise ValueError("ожидался обычный файл " + str(name))


def plan(root, source):
    add, keep, conflicts = {}, [], []
    append = None
    block = (KIT / "AGENTS.append.md").read_bytes()
    for name, data in source.items():
        file = root / name
        try:
            check_path(root, name)
            if not file.exists():
                add[name] = data
            elif name == ROOT_RULES:
                old = file.read_bytes()
                suffix = rules_suffix(old, data, block)
                if suffix:
                    if file.stat().st_nlink > 1:
                        raise ValueError("AGENTS.md имеет жёсткие ссылки; проверьте, какой файл должен получить инструкции")
                    append = (old, suffix)
                else:
                    keep.append(name)
            elif name == STANDARDS or file.read_bytes() == data:
                keep.append(name)
            else:
                conflicts.append(str(name) + " — файл уже существует с другим содержимым")
        except (ValueError, OSError) as error:
            conflicts.append(str(name) + " — " + str(error))
    return add, keep, append, conflicts


def apply(root, add, append):
    created_files, created_dirs = [], []
    try:
        for name, data in add.items():
            check_path(root, name)
            file = root / name
            for directory in reversed(file.parents):
                if root in directory.parents and not directory.exists():
                    directory.mkdir()
                    created_dirs.append(directory)
            # Исключительный режим защищает файлы, появившиеся после просмотра плана.
            with file.open("xb") as stream:
                created_files.append((file, data))
                stream.write(data)
        if append:
            original, suffix = append
            check_path(root, ROOT_RULES)
            with (root / ROOT_RULES).open("r+b") as stream:
                if stream.read() != original:
                    raise ValueError("AGENTS.md изменился во время установки")
                try:
                    stream.write(suffix)
                    stream.flush()
                except OSError:
                    stream.truncate(len(original))
                    raise
    except (OSError, ValueError):
        for file, data in reversed(created_files):
            if file.is_file() and not file.is_symlink() and data.startswith(file.read_bytes()):
                file.unlink()
        for directory in reversed(created_dirs):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, metavar="ПАПКА", help="существующая папка проекта")
    parser.add_argument("--apply", action="store_true", help="записать файлы по плану")
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Выберите существующую папку проекта")
    if root in (KIT, Path.home(), Path(root.anchor), Path.home() / ".codex", Path.home() / ".agents"):
        raise ValueError("Выберите отдельную рабочую папку проекта")
    add, keep, append, conflicts = plan(root, contents())
    print("Проект", root)
    for name in add:
        print("+", name)
    for name in keep:
        print("=", name, "(сохранить)")
    if append:
        print("+ AGENTS.md (дописать блок в конец)")
    if conflicts:
        raise ValueError("Конфликт, файлы проекта сохранены\n" + "\n".join(conflicts))
    if args.apply:
        apply(root, add, append)
        print("Подключено." if add or append else "Уже подключено.")
    else:
        print("Это план. Добавьте --apply для подключения.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
