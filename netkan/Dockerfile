FROM python:3.7 as base
RUN useradd -ms /bin/bash netkan
ADD . /netkan
WORKDIR /netkan
USER netkan
RUN pip install --user .
RUN python -m unittest -v
WORKDIR /
USER root
RUN rm -Rf /netkan

FROM python:3.7 as dev
RUN useradd -ms /bin/bash netkan
ADD . /netkan
WORKDIR /home/netkan
ADD run_dev.sh /usr/local/bin/
ENV PATH "$PATH:/home/netkan/.local/bin"
USER netkan
RUN pip install --user /netkan/.[development]

FROM python:3.7
COPY --from=base /home/netkan /home/netkan
RUN useradd -Ms /bin/bash netkan
RUN chown -R netkan:netkan /home/netkan
WORKDIR /home/netkan
USER netkan
ADD .gitconfig .
ENTRYPOINT [".local/bin/netkan"]
CMD ["--help"]
