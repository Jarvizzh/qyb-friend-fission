# 第一阶段：编译构建
FROM node:20-alpine as build-stage

WORKDIR /app

# 复制依赖配置并安装
COPY package*.json ./
RUN npm install

# 复制源代码并构建
COPY . .
# 生产环境通常需要将 API 地址指向服务器或通过 Nginx 代理
# 这里可以通过环境变量在构建时注入
RUN npm run build

# 第二阶段：使用 Nginx 托管静态资源
FROM nginx:stable-alpine

# 复制构建后的文件到 Nginx 目录
COPY --from=build-stage /app/dist /usr/share/nginx/html

# 复制自定义 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 暴露 80 端口
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
