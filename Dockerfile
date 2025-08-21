# image: https://docker.aityp.com/image/docker.io/python:3.12-slim?platform=linux/arm64
FROM python:3.12-slim

RUN useradd -m pyuser

WORKDIR /home/pyuser/phon

RUN chown -R pyuser:pyuser /usr/local/lib/python3.12/site-packages && \
    chown -R pyuser:pyuser /usr/local/bin && \
    chown -R pyuser:pyuser /home/pyuser/phon

USER pyuser

COPY --chown=pyuser:pyuser requirements.txt phon.py ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY --chown=pyuser:pyuser ./pyphon /home/pyuser/phon/pyphon/
COPY --chown=pyuser:pyuser ./web /home/pyuser/phon/web/
RUN mkdir -p config logs

CMD ["python", "phon.py"]
