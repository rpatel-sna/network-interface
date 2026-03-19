FROM almalinux:10.1

RUN dnf install -y python3.11 python3.11-pip gcc mariadb-devel && \
    dnf clean all

WORKDIR /app
COPY requirements.txt .
RUN pip3.11 install -r requirements.txt

COPY . .

CMD ["tail", "-f", "/dev/null"]
