#!/usr/bin/env python3
"""
Скрипт для упразднения уровня LUX_1 (дистрикты).
Кантоны (LUX_2) будут ссылаться напрямую на страну (LUX_0).

Что делает:
1. LUX_2 -> становится LUX_1 (кантоны теперь на уровне 1)
2. LUX_3 -> становится LUX_2 (коммуны теперь на уровне 2)
3. Старый LUX_1 (дистрикты) удаляется
"""
import json
import os
import shutil

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
    # Бэкап оригинальных файлов
    backup_dir = os.path.join(GEOFILES_DIR, 'backup')
    os.makedirs(backup_dir, exist_ok=True)

    for f in ['gadm41_LUX_1.json', 'gadm41_LUX_2.json', 'gadm41_LUX_3.json']:
        src = os.path.join(GEOFILES_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, f))
            print(f"Backup: {f}")

    # LUX_2 (кантоны) -> LUX_1
    shift_level(
        os.path.join(GEOFILES_DIR, 'gadm41_LUX_2.json'),
        os.path.join(GEOFILES_DIR, 'gadm41_LUX_1_new.json')
    )

    # LUX_3 (коммуны) -> LUX_2
    shift_level(
        os.path.join(GEOFILES_DIR, 'gadm41_LUX_3.json'),
        os.path.join(GEOFILES_DIR, 'gadm41_LUX_2_new.json')
    )

    # Заменяем файлы
    os.replace(
        os.path.join(GEOFILES_DIR, 'gadm41_LUX_1_new.json'),
        os.path.join(GEOFILES_DIR, 'gadm41_LUX_1.json')
    )
    os.replace(
        os.path.join(GEOFILES_DIR, 'gadm41_LUX_2_new.json'),
        os.path.join(GEOFILES_DIR, 'gadm41_LUX_2.json')
    )

    # Удаляем старый LUX_3
    os.remove(os.path.join(GEOFILES_DIR, 'gadm41_LUX_3.json'))

    print("\nDone! Hierarchy flattened:")
    print("  Old LUX_1 (districts) -> removed")
    print("  Old LUX_2 (cantons) -> new LUX_1")
    print("  Old LUX_3 (communes) -> new LUX_2")
    print("\nBackups saved in:", backup_dir)


if __name__ == '__main__':
    main()
