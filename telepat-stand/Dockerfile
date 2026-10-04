FROM mcr.microsoft.com/playwright:v1.62.1-noble
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --ignore-scripts && chown -R pwuser:pwuser /app
COPY --chown=pwuser:pwuser server.cjs viewer.html mask.js ./
USER pwuser
ENV NODE_ENV=production
EXPOSE 10000
CMD ["node","server.cjs"]
