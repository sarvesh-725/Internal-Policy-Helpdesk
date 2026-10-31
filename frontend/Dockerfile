FROM node:22-alpine

WORKDIR /app
COPY package.json .
RUN npm install
COPY . .

ENV VITE_API_BASE_URL=http://localhost:8000/api/v1
ENV VITE_KEYCLOAK_URL=http://localhost:8080
ENV VITE_KEYCLOAK_REALM=nodeswarm
ENV VITE_KEYCLOAK_CLIENT_ID=nodeswarm-web

EXPOSE 5173
CMD ["npm", "run", "dev"]
