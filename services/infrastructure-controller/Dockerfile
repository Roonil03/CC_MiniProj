# syntax=docker/dockerfile:1
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/controller ./cmd/controller

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /app
COPY --from=build /out/controller /app/controller
USER nonroot:nonroot
EXPOSE 8081
ENTRYPOINT ["/app/controller"]
