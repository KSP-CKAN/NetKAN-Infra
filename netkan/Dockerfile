FROM python:3.7 as base
RUN useradd -ms /bin/bash netkan
ADD . /netkan
WORKDIR /netkan
RUN pip install pip --upgrade
RUN chown -R netkan:netkan /netkan
USER netkan
RUN pip install --user . --no-warn-script-location

FROM python:3.7 as production
COPY --from=base /home/netkan /home/netkan
RUN useradd -Ms /bin/bash netkan
RUN chown -R netkan:netkan /home/netkan
WORKDIR /home/netkan
USER netkan
ADD .gitconfig .
ENV PATH "$PATH:/home/netkan/.local/bin"
RUN /home/netkan/.local/bin/netkan --help
ENTRYPOINT [".local/bin/netkan"]
CMD ["--help"]

FROM production as test
USER root
RUN pip install pip --upgrade
ADD . /netkan
RUN chown -R netkan:netkan /netkan
USER netkan
WORKDIR /netkan
RUN pip install --user .[test]
RUN /home/netkan/.local/bin/pytest --mypy -v

FROM production as dev
USER root
RUN pip install pip --upgrade
ADD . /netkan
RUN chown -R netkan:netkan /netkan
ADD run_dev.sh /usr/local/bin/
USER netkan
RUN pip install --user /netkan/.[development]
ENTRYPOINT ["/usr/local/bin/run_dev.sh"]

FROM production
