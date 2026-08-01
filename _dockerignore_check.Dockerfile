FROM alpine:3.19
COPY backend/data /out
RUN find /out -type f | sort
