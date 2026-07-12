FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /marzneshiniplimitcode

RUN apt-get update && apt install -y procps curl

COPY ./requirements.txt /marzneshiniplimitcode/

RUN pip install --no-cache-dir --upgrade -r /marzneshiniplimitcode/requirements.txt

COPY . /marzneshiniplimitcode

RUN chmod +x marzneshiniplimit.py api.py health_check.py

CMD ["bash", "-c", "python marzneshiniplimit.py & python api.py"]