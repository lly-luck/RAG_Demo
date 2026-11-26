import os
from datetime import datetime
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders.markdown import UnstructuredMarkdownLoader

# 自定义文本分割器
from rag_qa.edu_text_spliter import ChineseRecursiveTextSplitter, AliTextSplitter
from langchain_text_splitters import MarkdownTextSplitter
# 自定义OCR加载器（支持PDF/Word/PPT/图片）
from rag_qa.edu_document_loaders import OCRPDFLoader, OCRDOCLoader, OCRPPTLoader, OCRIMGLoader

# 项目基础配置与日志
from base.config import config as conf
from base.logger import logger

# ====================== 文件加载器映射表 ======================
# 支持的文件类型与对应加载器，统一管理便于扩展
document_loaders = {
    ".txt": TextLoader,
    ".pdf": OCRPDFLoader,
    ".docx": OCRDOCLoader,
    ".ppt": OCRPPTLoader,
    ".pptx": OCRPPTLoader,
    ".jpg": OCRIMGLoader,
    ".png": OCRIMGLoader,
    ".md": UnstructuredMarkdownLoader
}

def load_documents_from_directory(directory_path):
    """
    从指定目录递归加载所有支持的文档文件
    自动识别文件类型、添加元数据、异常捕获、日志记录
    :param directory_path: 文档根目录路径（如 data，包含 ai_data、java_data 等子目录）
    :return: LangChain Document 列表
    """
    # 定义存储原始文档的列表
    documents = []
    # 获取支持文档加载器支持的类型
    support_ext = document_loaders.keys()
    # 遍历原始文档的根目录
    for subject_dir in os.listdir(directory_path):
        # 拼接子目录的完整路径
        subject_path = os.path.join(directory_path, subject_dir)
        # 只处理子目录
        if not os.path.isdir(subject_path):
            continue
        # 获取技术方向来源
        source_subject = subject_dir.replace("_data", "")
        logger.info(f"开始处理技术方向：{source_subject}")
        # 递归遍历
        for dirpath, dirnames, filenames in os.walk(subject_path):
            for filename in filenames:
                # 获取文件具体路径
                file_path = os.path.join(dirpath, filename)
                # 截取文件的拓展名
                file_ext = os.path.splitext(file_path)[1].lower()
                # 判断文件拓展名是否支持
                if file_ext in support_ext:
                    # 获取对应文件加载器
                    loader_cls = document_loaders[file_ext]
                    # 加载文件
                    if loader_cls == ".txt":
                        loader = loader_cls(file_path, encoding="utf-8")
                    else:
                        loader = loader_cls(file_path)
                    loader_docs = loader.load()

                    # 为每份文档添加元数据（用于后续检测溯源）
                    for doc in loader_docs:
                        doc.metadata["source"] = source_subject
                        doc.metadata["file_path"] = file_path
                        doc.metadata["timestamp"] = datetime.now().isoformat()

                    # 合并到总文档列表
                    documents.extend(loader_docs)
                    logger.info(f"成功加载文件：{file_path}")
                else:
                    logger.warning(f"不支持此文件类型：{file_path}")

    logger.info(f"所有原始文档已加载完毕， 数量{len(documents)}")
    return documents


def process_documents(directory_path, parent_chunk_size=conf.PARENT_CHUNK_SIZE,
                      child_chunk_size=conf.CHILD_CHUNK_SIZE,
                      chunk_overlap=conf.CHUNK_OVERLAP):
    """
    文档分层分割核心函数（父子块结构）
    流程：加载文档 → 父块分割 → 子块分割 → 元数据绑定
    :param directory_path: 文档目录
    :param parent_chunk_size: 父块大小
    :param child_chunk_size: 子块大小
    :param chunk_overlap: 切块重叠长度
    :return: 带完整元数据的子块列表（用于向量入库）
    """
    # 根据路径加载原始文档
    documents = load_documents_from_directory(directory_path)
    # 创建文档分割器对象
    # 父块切割
    parent_splitter = ChineseRecursiveTextSplitter(chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap)
    md_parent_splitter = AliTextSplitter(chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap)
    # 子块切割
    child_splitter = ChineseRecursiveTextSplitter(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap)
    md_child_splitter = AliTextSplitter(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap)

    # 子块容器
    child_chunk = []

    # 遍历文档进行分割
    for i , doc in enumerate(documents):
        # 获取文档的文件类型
        file_path = doc.metadata.get("file_path", "")
        filr_ext = os.path.splitext(file_path)[1].lower()
        # 根据文件类型选择分割器
        id_md = filr_ext == ".md"
        parent_splitter_to_use = md_parent_splitter if id_md else parent_splitter
        child_splitter_to_use = md_child_splitter if id_md else child_splitter

        logger.info(f"处理文档{file_path}，分割器类型：{'Markdown' if id_md else 'ChineseRecursiveTextSplitter'}")

        # 对父块分割
        parent_docs = parent_splitter_to_use.split_documents([doc])
        # 遍历父块，并分割为子块
        for parent_i, parent_doc in enumerate(parent_docs):
            # 生成父块的id
            parent_id = f"doc_{i}_parent_{parent_i}"
            # 分割为子块
            child_docs = child_splitter_to_use.split_documents([parent_doc])
            # 封装子块的元数据
            for child_i, child_doc in enumerate(child_docs):
                child_doc.metadata["parent_id"]=parent_id
                child_doc.metadata["parent_content"]=parent_doc.page_content
                child_doc.metadata["id"]=f"{parent_id}_child_{child_i}"
                child_chunk.append(child_doc)

    logger.info(f"文档切割成功，总子块数量：{len(child_chunk)}")
    return child_chunk

if __name__ == '__main__':
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    process_documents(data_dir)







