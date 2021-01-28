FROM python:3.7 as base
RUN useradd -ms /bin/bash netkan
ADD . /netkan
WORKDIR /netkan
RUN pip install pip --upgrade
RUN pip install mypy
RUN chown -R netkan:netkan /netkan
USER netkan
RUN pip install --user . --no-warn-script-location
RUN mypy .
RUN python -m unittest -v
RUN /home/netkan/.local/bin/netkan --help

FROM python:3.7 as production
COPY --from=base /home/netkan /home/netkan
RUN useradd -Ms /bin/bash netkan
RUN chown -R netkan:netkan /home/netkan
WORKDIR /home/netkan
USER netkan
ADD .gitconfig .
ENV PATH "$PATH:/home/netkan/.local/bin"
ENTRYPOINT [".local/bin/netkan"]
CMD ["--help"]

FROM production as dev
USER root
ADD . /netkan
RUN chown -R netkan:netkan /netkan
ADD run_dev.sh /usr/local/bin/
USER netkan
RUN pip install --user /netkan/.[development]
RUN pip install --user /netkan/.[test]
ENTRYPOINT ["/usr/local/bin/run_dev.sh"]

FROM production
