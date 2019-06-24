FROM python:3.7

RUN mkdir /indexer
WORKDIR indexer
ADD . /indexer
RUN pip install .
WORKDIR /
RUN rm -Rf /indexer
RUN useradd -ms /bin/bash netkan
USER netkan
WORKDIR /home/netkan
ENTRYPOINT ["/usr/local/bin/netkan-indexer.py"]
