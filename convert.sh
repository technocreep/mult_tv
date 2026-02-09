#!/bin/bash

# Путь к папке с завершенными загрузками
BASE_DIR="/root/mult_tv/downloads/complete"
cd "$BASE_DIR" || exit

echo "--- Запуск умного сканирования аудиодорожек ---"

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

        # Используем ffprobe, чтобы найти индекс английской дорожки
        # Ищем по тегу language=eng или по названию (title) содержащему English
        track_index=$(ffprobe -v error -select_streams a -show_entries stream=index:tag=language,title -of csv=p=0 "$source_file" | \
            grep -iE "eng|english|orig" | head -n 1 | cut -d',' -f1)

        # Если дорожка не найдена, используем первую (индекс 0 в потоках аудио, т.е. 0:a:0)
        if [ -z "$track_index" ]; then
            echo "Английская дорожка не найдена, использую первую доступную."
            map_audio="0:a:0"
        else
            echo "Найдена подходящая дорожка (индекс $track_index)."
            map_audio="0:$track_index"
        fi

        echo "Конвертирую в MP4..."

        # Конвертация:
        # -map 0:v:0 (видео)
        # -map $map_audio (выбранное аудио)
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

chmod -R 777 /root/mult_tv/downloads
echo "--- Все операции завершены ---"
