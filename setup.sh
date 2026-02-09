#!/bin/bash

# 1. Создание структуры папок
echo "--- Создание папок проекта ---"
mkdir -p ~/mult_tv/app
mkdir -p ~/mult_tv/downloads
mkdir -p ~/mult_tv/watch
mkdir -p ~/mult_tv/config

# 2. Создание пустого файла базы данных
touch ~/mult_tv/app/history.db

echo "--- Настройка завершена! ---"
echo "Теперь мы готовы закидывать файлы бэкенда и запускать контейнеры."