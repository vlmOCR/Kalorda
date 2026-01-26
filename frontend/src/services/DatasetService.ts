import { get, post, postFile, postForm } from '@/utils/axios/HttpRequest'; //get,

export const DatasetService = {
    // 获取数据列表页
    async allDatasets(data: object) {
        let url = `/dataset/list`;
        return post(url, data);
    },
    async createDataset(data: object) {
        let url = `/dataset/create`;
        return post(url, data);
    },
    async updateDataset(data: object) {
        let url = `/dataset/update`;
        return post(url, data);
    },

    async delDataset(data: object) {
        let url = `/dataset/delete`;
        return post(url, data);
    },

    // 获取数据集详情
    async getDataset(dataset_id: number) {
        let url = `/dataset/${dataset_id}`;
        return get(url);
    },

    // 上传数据集文件
    async uploadDatasetFile(
        dataset_id: number | string, //数据集id
        file: File, //文件
        abortCallback?: Function, //控制请求中止
        progressCallback?: Function, //进度回调
        errorCallback?: Function, //出错回调
        finishedCallback?: Function //完成回调
    ) {
        let url = `/dataset/${dataset_id}/upload`;
        return postFile(url, file, abortCallback, progressCallback, errorCallback, finishedCallback);
    },

    async importDatasetZip(dataset_id: number | string, file: File, train_ratio: number | string) {
        let url = `/dataset/${dataset_id}/import`;
        let data = new FormData();
        data.append('file', file);
        data.append('train_ratio', String(train_ratio));
        return postForm(url, data, 180 * 1000);
    },

    // 启动后端数据集预处理流程
    async preprocess(dataset_id: number | string) {
        let url = `/dataset/${dataset_id}/preprocess`;
        return post(url, {});
    },

    async getDatasetImages(dataset_id: number | string, data: object) {
        let url = `/dataset/${dataset_id}/images`;
        return get(url, data);
    },

    async deleteDatasetImage(dataset_id: number | string, data: object) {
        let url = `/dataset/${dataset_id}/images/delete`;
        return post(url, data);
    },

    async moveDatasetImage(dataset_id: number | string, data: object) {
        let url = `/dataset/${dataset_id}/images/move`;
        return post(url, data);
    },

    // 获取所有图片序列id
    async getLabelImageIdList(data: object) {
        let url = `/dataset/label/image_id_list`;
        return get(url, data);
    },

    async getLabelImageUrlList(data: object) {
        let url = `/dataset/label/image_url_list`;
        return post(url, data);
    },

    // 获取单个图片信息
    async getLabelImageInfo(image_id: number | string) {
        let url = `/dataset/label/image_info/${image_id}`;
        return get(url);
    },

    // 保存图片标注结果
    async saveLabelData(data: object) {
        let url = `/dataset/label/save`;
        return post(url, data);
    }
};
