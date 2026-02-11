#!/bin/bash

# Использование:
#   ./convert.sh [директория] [язык]
#
# Примеры:
#   ./convert.sh                                              # по умолчанию: english
#   ./convert.sh /path/to/videos "rus|russian"                # русская дорожка
#   ./convert.sh /path/to/videos "eng|english|orig"           # английская дорожка

BASE_DIR="${1:-/root/mult_tv/mult_tv/downloads/complete}"
LANG_FILTER="${2:-eng|english|orig}"

cd "$BASE_DIR" || exit

echo "--- Запуск умного сканирования аудиодорожек ---"
echo "Директория: $BASE_DIR"
echo "Фильтр языка: $LANG_FILTER"

find . \( -name "*.mkv" -o -name "*.avi" \) -type f -print0 | while IFS= read -r -d '' source_file; do
    # Формируем имя mp4-файла (заменяем расширение)
    mp4_file="${source_file%.*}.mp4"

    if [ ! -f "$mp4_file" ]; then
        echo "Анализирую: $source_file"

        # Определяем кодек видео
        video_codec=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$source_file")
        echo "Видеокодек: $video_codec"

        # Если h264 — копируем без перекодирования, иначе перекодируем
        if [ "$video_codec" = "h264" ]; then
            video_opts="-c:v copy"
            echo "Кодек h264 — копирование без перекодирования."
        else
            video_opts="-c:v libx264 -preset medium -crf 23"
            echo "Кодек $video_codec — перекодирование в h264."
        fi

        # Ищем аудиодорожку по заданному языку
        track_index=$(ffprobe -v error -select_streams a -show_entries stream=index:stream_tags=language,title -of csv=p=0 "$source_file" | \
            grep -iE "$LANG_FILTER" | head -n 1 | cut -d',' -f1)

        # Если дорожка не найдена, используем первую
        if [ -z "$track_index" ]; then
            echo "Дорожка ($LANG_FILTER) не найдена, использую первую доступную."
            map_audio="0:a:0"
        else
            echo "Найдена подходящая дорожка (индекс $track_index)."
            map_audio="0:$track_index"
        fi

        echo "Конвертирую в MP4..."

        ffmpeg -nostdin -i "$source_file" \
            -map 0:v:0 -map "$map_audio" \
            $video_opts -c:a aac -ac 2 -b:a 192k \
            -movflags +faststart \
            -y -loglevel error "$mp4_file"

        if [ $? -eq 0 ]; then
            echo "Успешно создано: $mp4_file"
            rm "$source_file"
            echo "Удалён оригинал: $source_file"
        else
            echo "Ошибка при обработке: $source_file"
        fi
    fi
done

chmod -R 755 /root/mult_tv/downloads
echo "--- Все операции завершены ---"
