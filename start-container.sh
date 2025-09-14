sudo docker run -d --name facility-v1 --restart=always --net=host \
   -v /etc/timezone:/etc/timezone:ro \
   -v /etc/localtime:/etc/localtime:ro \
   -v /home/difinative/Management:/home/metro/Management \
   -e TZ=Asia/Kolkata \
   facility-image:1.0
