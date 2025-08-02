# image: https://docker.aityp.com/image/docker.io/python:3.12-slim?platform=linux/arm64
FROM python:3.12-slim

RUN useradd -m pyuser && \
    chown pyuser:pyuser /home/pyuser

WORKDIR /home/pyuser

RUN pip install --upgrade pip virtualenv && python -m venv venv

# COPY ./packages /home/pyuser/
RUN . venv/bin/activate && pip install --upgrade pip requests fastapi uvicorn rsa
#  && pip install *.whl && rm -f *.whl


WORKDIR /home/pyuser/phon
COPY --chown=pyuser:pyuser ./pyphon /home/pyuser/phon/pyphon/
COPY --chown=pyuser:pyuser ./web /home/pyuser/phon/web/
RUN mkdir -p /home/pyuser/phon/config /home/pyuser/phon/logs && \
    chown -R pyuser:pyuser /home/pyuser/phon && \
    chmod -R 755 /home/pyuser/phon

USER pyuser

CMD ["/home/pyuser/venv/bin/python", "pyphon/emtrader.py"]
