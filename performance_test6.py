import boto3
import time
import csv
from datetime import datetime, timedelta

s3 = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')
logs = boto3.client('logs')

def upload_test_images(bucket_name, num_images=100):
    """批量上传测试图片到S3桶"""
    for i in range(num_images):
        try:
            s3.upload_file(f'test_{i}.jpg', bucket_name, f'test_{i}.jpg')
            print(f'Uploaded test_{i}.jpg')
        except Exception as e:
            print(f"Error uploading test_{i}.jpg: {str(e)}")

def parse_memory_usage(function_name, start_time, end_time):
    """从CloudWatch Logs提取Max Memory Used"""
    log_group = f'/aws/lambda/{function_name}'
    memory_usage = []
    
    # 转换时间为毫秒时间戳
    start_ms = int((start_time - timedelta(minutes=15)).timestamp() * 1000) 
    end_ms = int(end_time.timestamp() * 1000) 

    try:
        response = logs.filter_log_events(
            logGroupName=log_group,
            startTime=start_ms,
            endTime=end_ms,
            filterPattern='REPORT Max Memory Used'
        )

        for event in response['events']:
            message = event['message']
            if 'Max Memory Used' in message:
                # 解析日志格式：Max Memory Used
                parts = [p.strip() for p in message.split('\t') if 'Max Memory Used' in p]
                if parts:
                    value_part = parts[0].split(':')[-1].strip()
                    mb_value = int(value_part.split(' ')[0])
                    memory_usage.append(mb_value)

    except Exception as e:
        print(f"Error parsing logs: {str(e)}")
    
    return memory_usage

def collect_metrics(function_name, memory_size, start_time):
    """收集指标数据"""
    end_time = datetime.utcnow()
    metrics = {
        'Duration': [],
        'Billed Duration': [],
        'Max Memory Used': []
    }

    # 获取Duration
    for metric_name in ['Duration', 'Billed Duration']:
        try:
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName=metric_name,
                Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                StartTime=start_time - timedelta(minutes=15),
                EndTime=end_time,
                Period=60,
                Statistics=['Average']
            )
            metrics[metric_name] = response['Datapoints']
        except Exception as e:
            print(f"Error getting {metric_name} metrics: {str(e)}")

    # 从日志获取内存使用数据
    try:
        metrics['Max Memory Used'] = parse_memory_usage(
            function_name, 
            start_time,
            end_time
        )
    except Exception as e:
        print(f"Error getting memory usage: {str(e)}")

    return metrics

def generate_report(data, output_file='report1.csv'):
    """生成最终报告"""
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            'Memory (MB)', 
            'Avg Duration (ms)', 
            'Max Memory Used (MB)', 
            'Cost per 1M Invocations'
        ])
        
        for config in data:
            # 计算平均持续时间
            duration_data = config['metrics']['Duration']
            avg_duration = 0
            if duration_data:
                avg_duration = sum([dp['Average'] for dp in duration_data]) / len(duration_data)

            # 获取最大内存使用量
            memory_data = config['metrics']['Max Memory Used']
            max_memory = max(memory_data) if memory_data else 0

            # 成本计算
            memory_gb = config['memory'] / 1024
            request_cost = 0.20  # 每百万请求固定费用
            compute_seconds = (avg_duration / 1000) * 1000000  # 总计算时间（秒）
            compute_cost = compute_seconds * memory_gb * 0.0000166667
            total_cost = request_cost + compute_cost

            writer.writerow([
                config['memory'],
                round(avg_duration, 2),
                max_memory,
                round(total_cost, 2)
            ])

def main():
    bucket_name = 'lambda-picture-input'          # 修改为你的S3桶名称
    function_name = 'thumbnail'                         # 修改为你的Lambda函数名称
    memory_configs = [128, 512, 1024]

    test_data = []
    
    for memory in memory_configs:
        print(f"\nTesting {memory}MB configuration...")
        
        # 更新Lambda配置
        lambda_client = boto3.client('lambda')
        try:
            lambda_client.update_function_configuration(
                FunctionName=function_name,
                MemorySize=memory
            )
            print(f"Updated Lambda memory to {memory}MB")
        except Exception as e:
            print(f"Error updating Lambda: {str(e)}")
            continue
        
        # 等待配置生效和冷启动
        time.sleep(60)
        
        # 上传测试文件并记录开始时间
        start_time = datetime.utcnow()
        try:
            upload_test_images(bucket_name)
        except Exception as e:
            print(f"Error uploading images: {str(e)}")
            continue
        
        # 确保日志生成
        print("Waiting for logs to be available...")
        time.sleep(120) 
        
        # 收集指标
        try:
            metrics = collect_metrics(function_name, memory, start_time)
            test_data.append({
                'memory': memory,
                'metrics': metrics
            })
            print(f"Collected metrics for {memory}MB config")
        except Exception as e:
            print(f"Error collecting metrics: {str(e)}")

    # 生成最终报告
    try:
        generate_report(test_data)
        print("\nReport generated successfully!")
    except Exception as e:
        print(f"Error generating report: {str(e)}")

if __name__ == '__main__':
    main()