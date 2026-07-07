#!/usr/bin/env python3
"""
Скрипт для упразднения одного уровня иерархии GADM extract'а.
Уровень N+1 будет ссылаться напрямую на уровень N-1.

Что делает (для страны с кодом <ISO>, упраздняя уровень 1):
1. <ISO>_2 -> становится <ISO>_1
2. <ISO>_3 -> становится <ISO>_2
3. Старый <ISO>_1 удаляется

Usage: flatten_hierarchy.py <ISO3-code>
"""
import json
import os
import shutil
import sys

GEOFILES_DIR = os.path.dirname(os.path.abspath(__file__))


def shift_level(input_file, output_file, level_shift=-1):
    """Сдвигает уровень на level_shift (по умолчанию -1, т.е. вверх)"""
    with open(input_file, 'r') as f:
        data = json.load(f)

    # Изменяем имя файла в name
    old_name = data.get('name', '')
    parts = old_name.rsplit('_', 1)
    if len(parts) == 2:
        old_level = int(parts[1])
        new_level = old_level + level_shift
        data['name'] = f"{parts[0]}_{new_level}"

    for feature in data['features']:
        props = feature['properties']
        new_props = {}

        # Сохраняем GID_0 и COUNTRY как есть
        if 'GID_0' in props:
            new_props['GID_0'] = props['GID_0']
        if 'COUNTRY' in props:
            new_props['COUNTRY'] = props['COUNTRY']

        for key, value in props.items():
            # Пропускаем уже обработанные
            if key in ('GID_0', 'COUNTRY'):
                continue
            # GID_X -> GID_(X-1), но пропускаем GID_1 (дистрикты удаляем)
            if key.startswith('GID_'):
                level = int(key.split('_')[1])
                if level == 1:
                    continue  # пропускаем ссылку на дистрикт
                new_level = level + level_shift
                if new_level >= 0:
                    new_props[f'GID_{new_level}'] = value
            # NAME_X, TYPE_X, VARNAME_X, etc -> _(X-1), пропускаем _1
            elif '_' in key and key.split('_')[-1].isdigit():
                prefix = '_'.join(key.split('_')[:-1])
                level = int(key.split('_')[-1])
                if level == 1:
                    continue  # пропускаем данные дистрикта
                new_level = level + level_shift
                if new_level >= 0:
                    new_props[f'{prefix}_{new_level}'] = value
            # Остальные поля копируем как есть
            else:
                new_props[key] = value

        feature['properties'] = new_props

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Created: {output_file}")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <ISO3-code>", file=sys.stderr)
        sys.exit(1)
    iso = sys.argv[1].upper()

    # Бэкап оригинальных файлов
    backup_dir = os.path.join(GEOFILES_DIR, 'backup')
    os.makedirs(backup_dir, exist_ok=True)

    for level in (1, 2, 3):
        f = f'gadm41_{iso}_{level}.json'
        src = os.path.join(GEOFILES_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, f))
            print(f"Backup: {f}")

    # level 2 (кантоны) -> level 1
    shift_level(
        os.path.join(GEOFILES_DIR, f'gadm41_{iso}_2.json'),
        os.path.join(GEOFILES_DIR, f'gadm41_{iso}_1_new.json')
    )

    # level 3 (коммуны) -> level 2
    shift_level(
        os.path.join(GEOFILES_DIR, f'gadm41_{iso}_3.json'),
        os.path.join(GEOFILES_DIR, f'gadm41_{iso}_2_new.json')
    )

    # Заменяем файлы
    os.replace(
        os.path.join(GEOFILES_DIR, f'gadm41_{iso}_1_new.json'),
        os.path.join(GEOFILES_DIR, f'gadm41_{iso}_1.json')
    )
    os.replace(
        os.path.join(GEOFILES_DIR, f'gadm41_{iso}_2_new.json'),
        os.path.join(GEOFILES_DIR, f'gadm41_{iso}_2.json')
    )

    # Удаляем старый level 3
    os.remove(os.path.join(GEOFILES_DIR, f'gadm41_{iso}_3.json'))

    print("\nDone! Hierarchy flattened:")
    print("  Old level 1 (districts) -> removed")
    print("  Old level 2 (cantons) -> new level 1")
    print("  Old level 3 (communes) -> new level 2")
    print("\nBackups saved in:", backup_dir)


if __name__ == '__main__':
    main()
