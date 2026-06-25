from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options_vlm_model import ApiVlmOptions, ResponseFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline

vllm_options = ApiVlmOptions(
    url="http://ec2-3-85-241-207.compute-1.amazonaws.com:8000/v1/chat/completions",
    model="ibm-granite/granite-docling-258M",
    prompt="Convert this page to DocTags.",
    response_format=ResponseFormat.DOCTAGS,
    timeout=120.0,
)

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_cls=VlmPipeline,
            vlm_options=vllm_options,
        ),
    }
)

result = converter.convert(r"C:\Users\varun\Downloads\Pup Jt - PO.pdf")
print(result.document.export_to_markdown())