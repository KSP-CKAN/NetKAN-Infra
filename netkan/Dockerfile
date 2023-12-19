FROM ubuntu:latest as ubuntu_with_python

# Don't prompt for time zone
ENV DEBIAN_FRONTEND=noninteractive

# Install Git and Python
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git libffi-dev openssh-client \
        python3 python-is-python3 \
    && apt-get clean

FROM ubuntu_with_python as base
RUN apt-get install -y --no-install-recommends \
    python3-pip python3-setuptools python3-dev
RUN useradd -ms /bin/bash netkan
ADD . /netkan
WORKDIR /netkan
RUN pip install pip --upgrade
RUN chown -R netkan:netkan /netkan
USER netkan
RUN pip install --user . --no-warn-script-location

FROM ubuntu_with_python as production
COPY --from=base /home/netkan/.local /home/netkan/.local
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
RUN apt-get install -y --no-install-recommends \
    python3-pip python3-setuptools python3-dev
RUN pip install pip --upgrade
ADD . /netkan
RUN chown -R netkan:netkan /netkan
USER netkan
WORKDIR /netkan
RUN pip install --user .[test]
RUN /home/netkan/.local/bin/pytest -v

FROM production as dev
USER root
RUN apt-get install -y --no-install-recommends \
    python3-pip python3-setuptools python3-dev
RUN pip install pip --upgrade
ADD . /netkan
RUN chown -R netkan:netkan /netkan
ADD run_dev.sh /usr/local/bin/
USER netkan
RUN pip install --user /netkan/.[development]
ENTRYPOINT ["/usr/local/bin/run_dev.sh"]

FROM production
